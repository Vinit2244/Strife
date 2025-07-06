import os
from concurrent import futures
from loguru import logger
import argparse
import grpc
import sys
import datetime
import requests
import logging

from pathlib import Path

RED = '\033[0;31m'
GREEN = '\033[0;32m'
RESET = '\033[0m'

# Get the absolute path of the current script
script_dir = Path(__file__).parent

sys.path.append("generated")
import bank_pb2
import bank_pb2_grpc as bank_grpc
import payment_gateway_pb2
import payment_gateway_pb2_grpc as payment_gateway_grpc

class Bank:
    def __init__(self, port):
        self.id = -1
        self.port = port
        self.clients = []

    def generateUniqueAccountNumber(self):
        if self.clients == []:
            max_account_number = 0
        else:
            max_account_number = max([client.account_number for client in self.clients])
        return str(max_account_number + 1)

    def createNewAccount(self, username, password, initial_balance=0):
        # Check if username is not empty
        if username == "":
            logger.error("Username cannot be empty")
            return 1, "Username cannot be empty"
        
        # Check if password is empty
        if password == "":
            logger.error("Password cannot be empty")
            return 1, "Password cannot be empty"
        
        # Check if initial balance is negative
        if initial_balance < 0:
            logger.error("Initial balance must be >= 0")
            return 1, "Inital balance must be non negative"
        account_number = self.generateUniqueAccountNumber()
        new_client = Client(username, password, account_number)
        new_client.setBalance(initial_balance)
        self.clients.append(new_client)
        return 0, account_number

    def checkAccountExist(self, account_number):
        return True if account_number in [client.getAccountNumber() for client in self.clients] else False
    
    def getID(self):
        return self.id
    
    def setID(self, id):
        self.id = id

    def getAllClients(self):
        return self.clients

    def getClientByUsername(self, username):
        for client in self.clients:
            if client.getUsername() == username:
                return client
        return None


class Client:
    def __init__(self, username, password, account_number):
        self.username = username
        self.password = password
        self.account_number = int(account_number)
        self.balance = 0
        self.acc_statement = []

    def credit(self, amount):
        if amount < 0:
            logger.error(f"Amount to be credited should be >= 0, but got amount = {amount}")
            return 1
        self.balance += amount
        return 0
        
    def debit(self, amount):
        if amount <= 0:
            logger.error(f"Amount to be debited should be > 0, but got amount = {amount}")
            return 1
        elif self.balance < amount:
            logger.error(f"Not enough balance in account :(")
            return 1
        self.balance -= amount
        return 0
        
    def getBalance(self):
        return self.balance
    
    def setBalance(self, balance):
        self.balance = balance

    def getAccountNumber(self):
        return str(self.account_number)

    def getUsername(self):
        return self.username

    def checkPassword(self, entered_password):
        return entered_password == self.password

    def addTransaction(self, transaction):
        self.acc_statement.append(transaction)

    def getAllTransactions(self):
        return self.acc_statement


class BankServicer(bank_grpc.BankServicer):
    def CreateNewClient(self, request, context):
        logger.info("Create new client request received")
        response_obj = bank_pb2.CreateNewClientResponse()
        err_code, output = MyBank.createNewAccount(request.username, request.password, request.initial_balance)
        if err_code == 1:
            logger.error(output)
            response_obj.err_code = 1
            response_obj.text = output
        else:
            logger.info(f"New client created successfully with account number = {output}")
            response_obj.err_code = 0
            response_obj.account_number = str(output)

        return response_obj

    def VerifyClientInfo(self, request, context):
        logger.info("Verify client info request received")
        response_obj = bank_pb2.ClientInformationResponse()
        response_obj.present = False

        for client in MyBank.getAllClients():
            if client.getUsername() == request.username and client.getAccountNumber() == request.account_number and client.checkPassword(request.password):
                response_obj.present = True
                logger.info("Client found")
                break
        if response_obj.present == False:
            logger.info("Client not found")
        return response_obj

    def FetchBalance(self, request, context):
        logger.info("Fetch balance request received")
        response_obj = bank_pb2.FetchBalanceResponse()

        clients = MyBank.getAllClients()
        for client in clients:
            if client.getAccountNumber() == request.account_number:
                logger.info(f"Found client; Balance = {client.getBalance()}")
                response_obj.err_code = 0
                response_obj.balance = client.getBalance()
                return response_obj
            
        logger.error("Client not found")
        response_obj.err_code = 1
        response_obj.text = "Client not found"
        return response_obj

    def AddBalance(self, request, context):
        logger.info("Add Balance request received")

        client = MyBank.getClientByUsername(request.username)
        client.credit(request.amount)

        response_obj = bank_pb2.AddBalanceResponse(err_code=0, text="")
        return response_obj

    def Credit(self, request, context):
        logger.info("Credit request received")

        response_obj = bank_pb2.AmountTransferResponse()
        client = MyBank.getClientByUsername(request.receiver_username)
        if client is None:
            response_obj.err_code = 1
            response_obj.text = "No such client exist"
            logger.error("No such client exists")
            return response_obj
        
        err_code = client.credit(request.amount)
        if err_code == 1:
            response_obj.err_code = err_code
            response_obj.text = "Invalid amount"
            return response_obj

        now = datetime.datetime.now()
        formatted_time = now.strftime("%B %d, %Y - %H:%M:%S")
        if request.type == "deposit":
            client.addTransaction(f"{GREEN}{formatted_time} : {request.amount} deposited in account{RESET}")
            
        elif request.type == "transfer":
            client.addTransaction(f"{GREEN}{formatted_time} : {request.amount} credited from {request.sender_username} | Bank id: {request.sender_bank_id} | Acc No: {request.sender_acc_no}{RESET}")
            
        elif request.type == "reimbursement":
            client.addTransaction(f"{GREEN}{formatted_time} : {request.amount} recredited in account{RESET}")
        
        response_obj.err_code = 0
        response_obj.text = "Amount Credited"
        response_obj.balance = client.getBalance()
        return response_obj

    def Debit(self, request, context):
        logger.info("Debit request received")

        response_obj = bank_pb2.AmountTransferResponse()
        
        client = MyBank.getClientByUsername(request.sender_username)
        if client is None:
            response_obj.err_code = 1
            response_obj.text = "No such client exist"
            logger.error("No such client exists")
            return response_obj
        
        err_code = client.debit(request.amount)
        if err_code == 1:
            response_obj.err_code = err_code
            response_obj.text = "Not enough balance in account"
            return response_obj
        
        now = datetime.datetime.now()
        formatted_time = now.strftime("%B %d, %Y - %H:%M:%S")
        
        if request.type == "withdraw":
            client.addTransaction(f"{RED}{formatted_time} : {request.amount} withdrawn in account{RESET}")
            
        elif request.type == "transfer":
            client.addTransaction(f"{RED}{formatted_time} : {request.amount} debited to {request.receiver_username} | Bank id: {request.receiver_bank_id} | Acc No: {request.receiver_acc_no}{RESET}")
        
        response_obj.err_code = 0
        response_obj.text = "Amount Debited"
        response_obj.balance = client.getBalance()
        return response_obj

    def GetTransactions(self, request, context):
        logger.info("Get Transactions request received")
        response_obj = bank_pb2.TransactionsResponse()
        client = MyBank.getClientByUsername(request.username)
        if client is None:
            response_obj.err_code = 1
            response_obj.text = "No such user exist"
            return response_obj
        response_obj.err_code = 0
        response_obj.transactions.extend(client.getAllTransactions())
        return response_obj

    def CheckClientExist(self, request, context):
        logger.info("Check client exists request received")

        response_obj = bank_pb2.CheckClientExistResponse()

        client = MyBank.getClientByUsername(request.username)
        if client is None:
            response_obj.err_code = 1
            response_obj.text = "Client does not exist"
            logger.error("Client does not exist")
        
        else:
            if client.getUsername() == request.username and client.getAccountNumber() == request.acc_no:
                response_obj.err_code = 0
                response_obj.text = "Client Exists"
                logger.info("Client Exists")
            else:
                response_obj.err_code = 1
                response_obj.text = "Invalid Information"
                logger.error("Invalid Information")
        return response_obj


# =========================================================================================
# Base code generated by ChatGPT + Modified by me (Prompt 1 in README)
# =========================================================================================
logging.basicConfig(
    filename="./server/logs/bank_server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

class LoggingInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)

        # Extract details
        method_name = handler_call_details.method
        username = metadata.get("username", "Unknown")

        logging.info(f"Received request: {method_name}")
        logging.info(f"Username: {username}")
        
        try:
            response = continuation(handler_call_details)
            return response
        except Exception as e:
            logging.error(f"Error in {method_name}: {str(e)}")
            raise e
# =========================================================================================


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    bank_grpc.add_BankServicer_to_server(BankServicer(), server)

    server.add_insecure_port(f"localhost:{my_port}")
    server.start()
    logger.info(f"Bank server started; Port = {my_port}")

    # Registering bank with payment gateway
    root_certificate_relative_path = "../CA/ca.crt"
    file_path = script_dir / root_certificate_relative_path
    with open(file_path, "rb") as f:
        trusted_certs = f.read()

    credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)
    channel = grpc.secure_channel(f"localhost:{gateway_port}", credentials)
    gateway_stub = payment_gateway_grpc.PaymentGatewayStub(channel)
    request_obj = payment_gateway_pb2.RegisterBankRequest()
    request_obj.port = my_port
    public_ip = requests.get("https://api64.ipify.org").text

    metadata = [
        ("authorization", "bank"),
        ("ip", public_ip),
        ("amount", str(0))
        ]
    response = gateway_stub.RegisterBank(request_obj, metadata=metadata)
    if response.err_code == 0:
        logger.info(f"Bank registered successfully with id = {response.id}")
        MyBank.setID(response.id)
    else:
        logger.error(response.text)
    channel.close()

    server.wait_for_termination()

if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:MMMM D, YYYY - HH:mm:ss} {level} --- <level>{message}</level>")

    parser = argparse.ArgumentParser(description="Start the Bank gRPC Server")
    parser.add_argument("--port", type=int, default=50052, help="Port number to run the gRPC server on")
    parser.add_argument("--gatewayport", type=int, default=-1, help="Port on which payment gateway is listening")

    args = parser.parse_args()

    global my_port
    my_port = args.port

    global gateway_port
    gateway_port = args.gatewayport

    global MyBank
    MyBank = Bank(my_port)
    
    clear_screen()
    serve()