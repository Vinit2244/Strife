import os
from loguru import logger
import argparse
from pathlib import Path
import requests
import time
import random

# Get the absolute path of the current script
script_dir = Path(__file__).parent

import sys
sys.path.append("generated")

import grpc
import payment_gateway_pb2
import payment_gateway_pb2_grpc as payment_gateway_grpc

WAIT_TIME_FACTOR_S = 1  # Waiting time proportionality factor in seconds
TIMEOUT_S = 2           # Timeout in seconds
MAX_TRIES = 3

gateway_stub = None

class SessionManager:
    def __init__(self, ip):
        self.ip = ip
        self.channel = None

    def __enter__(self):
        global gateway_stub
        root_certificate_relative_path = "../CA/ca.crt"
        file_path = script_dir / root_certificate_relative_path
        with open(file_path, "rb") as f:
            trusted_certs = f.read()

        credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)
        self.channel = grpc.secure_channel(self.ip, credentials)
        gateway_stub = payment_gateway_grpc.PaymentGatewayStub(self.channel)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.channel:
            self.channel.close()

# def wait_milliseconds(milliseconds):
#     seconds = milliseconds / 1000
#     time.sleep(seconds)

# Wrapper for implementing idempotency for all types of request except 
# authentication - it's case is handled separately in it's own function
def send_request_get_response(function, request, metadata):
    tries = 0
    while True:
        tries += 1

        # Exponential backoff + jitter
        time_to_wait_for_response_before_retry = (WAIT_TIME_FACTOR_S * (2 ** tries)) + random.random()
        try:
            response = function(request, metadata=metadata, timeout=time_to_wait_for_response_before_retry)
            return response
        except Exception as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                print("Request failed, retrying...")
            else:
                print(f"RPC Failes: {e}, retrying...")
            continue


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def wait_for_enter():
    print()
    print("Press Enter to continue...", end="", flush=True)
    while True:
        char = sys.stdin.read(1)    # Reads one character at a time
        if char == "\n":            # Only proceed if Enter is pressed
            break

def authenticate(username, password):
    public_ip = requests.get("https://api64.ipify.org").text

    metadata_auth = [
        ("authorization", "auth"),
        ("amount", str(0)),
        ("ip", public_ip)
        ]

    tries = 0
    while True:
        tries += 1

        # Exponential backoff + jitter
        time_to_wait_for_response_before_retry = (WAIT_TIME_FACTOR_S * (2 ** tries)) + random.random()
        try:
            response, call = gateway_stub.Authenticate.with_call(
                request = payment_gateway_pb2.AuthRequest(username=username, password=password),
                metadata = metadata_auth,
                timeout = TIMEOUT_S
            )
            break
        except Exception as e:
            if tries < MAX_TRIES:
                print("Request failed, retrying...\n")
                time.sleep(time_to_wait_for_response_before_retry)
            else:
                print(f"RPC Failed: {e}")
                return None

    global metadata
    metadata = call.initial_metadata()

    return response

def check_balance():
    request_obj = payment_gateway_pb2.CheckBalanceRequest()

    response  = send_request_get_response(gateway_stub.CheckBalance, request_obj, metadata)
    # response = gateway_stub.CheckBalance(request_obj, metadata=metadata)

    if response.err_code == 1:
        logger.error(response.text)
    else:
        logger.info(f"Balance = {response.balance}")
    wait_for_enter()

def register(username, password, bank_id, account_number):
    if not validateInput(username=username, password=password, bank_id=bank_id, account_number=account_number):
        return
    
    request_obj = payment_gateway_pb2.RegisterClientRequest()
    request_obj.username = str(username)
    request_obj.account_number = str(account_number)
    request_obj.password = str(password)
    request_obj.bank_id = int(bank_id)

    response = gateway_stub.RegisterClient(request_obj)

    if response.err_code == 1:
        logger.error(response.text)
    else:
        logger.info("Client registered successfully")
    wait_for_enter()

def AdminAccess_create_new_client(username, password):
    new_username = input("Enter new client username: ")
    new_password = input("Enter new client password: ")
    new_client_bank_id = input("Enter new client bank id: ")
    initial_balance = input("Enter initial account balance: ")

    if not validateInput(username=new_username, password=new_password, bank_id=new_client_bank_id, balance=initial_balance):
        return
    
    request_obj = payment_gateway_pb2.CreateNewClientRequest()
    request_obj.admin_username = username
    request_obj.admin_password = password
    request_obj.new_client_username = new_username
    request_obj.new_client_password = new_password
    request_obj.new_client_bank_id = int(new_client_bank_id)
    request_obj.initial_balance = float(initial_balance)

    response = gateway_stub.AdminAccessCreateNewClient(request_obj, metadata=update_amount_in_metadata(initial_balance))

    if response.err_code == 1:
        logger.error(response.text)
    else:
        logger.info(f"New client created successfully with account number = {response.account_number}")
    wait_for_enter()

def update_amount_in_metadata(new_amount):
    metadata_dict = dict(metadata)
    metadata_dict["amount"] = str(new_amount)
    updated_metadata = list(metadata_dict.items())
    return updated_metadata

def AdminAccess_add_money():
    client_username = input("Enter username of client: ")
    amount = input("Enter amount: ")

    if not validateInput(username=client_username, balance=amount):
        return
    
    request_obj = payment_gateway_pb2.AddBalanceRequest()
    request_obj.username = client_username
    request_obj.amount = float(amount)

    response = gateway_stub.AdminAccessAddBalance(request_obj, metadata=update_amount_in_metadata(amount))

    if response.err_code == 1:
        logger.error(response.text)
        wait_for_enter()
    else:
        logger.info(f"{amount} credited in {client_username}'s account successfully")
        wait_for_enter()

def transfer_amount(receiver_username, receiver_bank_id, receiver_acc_no, amount_to_be_transferred):
    if not validateInput(username=receiver_username, bank_id=receiver_bank_id, account_number=receiver_acc_no, balance=amount_to_be_transferred):
        logger.error("Invalid Input")
        return
    
    request_obj = payment_gateway_pb2.TransferAmountRequest()
    request_obj.receiver_username = receiver_username
    request_obj.receiver_bank_id = int(receiver_bank_id)
    request_obj.receiver_acc_no = receiver_acc_no
    request_obj.amount = float(amount_to_be_transferred)
    request_obj.type = "transfer"

    response = gateway_stub.TransferAmount(request_obj, metadata=update_amount_in_metadata(amount_to_be_transferred))

    if response.err_code == 1:
        logger.error(response.text)
    else:
        logger.info(f"Transferred successfully remaining balance = {response.balance}")
    wait_for_enter()

def deposit(amount):
    if not validateInput(balance=amount):
        logger.error("Invalid amount")
        return
    request_obj = payment_gateway_pb2.TransferAmountRequest()
    request_obj.amount = float(amount)
    response = gateway_stub.Deposit(request_obj, metadata=update_amount_in_metadata(amount))

    if response.err_code == 1:
        logger.error(response.text)
    else:
        logger.info(f"Amount deposited successfully, final balance = {response.balance}")
    wait_for_enter()

def withdraw(amount):
    if not validateInput(balance=amount):
        logger.error("Invalid amount")
        return
    
    request_obj = payment_gateway_pb2.TransferAmountRequest()
    request_obj.amount = float(amount)

    response = gateway_stub.Withdraw(request_obj, metadata=update_amount_in_metadata(amount))

    if response.err_code == 1:
        logger.error(response.text)
    else:
        logger.info(f"Amount withdrawn successfully, final balance = {response.balance}")
    wait_for_enter()

def get_account_statement():
    request_obj = payment_gateway_pb2.TransactionHistoryRequest()
    response = gateway_stub.GetTransactionHistory(request_obj, metadata=metadata)

    if response.err_code == 1:
        logger.error(response.text)
    else:
        transactions = response.transactions
        for transaction in transactions:
            print(transaction)
            print()
    wait_for_enter()

def validateInput(username=None, password=None, bank_id=None, account_number=None, balance=None):
    # Check for username
    if username is not None:
        if username.strip() == "":
            logger.error("Username cannot be empty")
            wait_for_enter()
            return False
        
    # Check for password
    if password is not None:
        if password == "":
            logger.error("Password cannot be empty")
            wait_for_enter()
            return False
        
    # Check for bank id
    if bank_id is not None:
        try:
            bank_id = int(bank_id)
            if bank_id < 0:
                logger.error("Bank ID must be non-negative")
                wait_for_enter()
                return False
        except:
            logger.error("Bank ID must be an integer")
            wait_for_enter()
            return False
        
    # Check for account number
    if account_number is not None:
        try:
            account_number = int(account_number)
            if account_number <= 0:
                logger.error("Account Number should be positive")
                wait_for_enter()
                return False
        except:
            logger.error("Account number should be an integer")
            wait_for_enter()
            return False

    # Check for balance
    if balance is not None:
        try:
            balance = float(balance)
            if balance < 0:
                logger.error("Balance should be non-negative")
                wait_for_enter()
                return False
        except:
            logger.error("Balance should be float")
            wait_for_enter()
            return False
    
    return True

def menu():
    role = None

    while True:
        clear_screen()

        print("What do you want to do? (Type 'exit' to exit)")
        print("  1. Authenticate")
        print("  2. Register with payment gateway")
        print()
        opt = input("Enter your choice: ").strip()
        print()

        if opt == "1":
            username = input("Enter your username: ").strip()
            password = input("Enter your password: ")
            response = authenticate(username, password)
            if response is None:
                logger.error("Authentication failed!")
                wait_for_enter()
                continue
            if response.err_code == 1:
                logger.error(f"Authentication failed! {response.text}")
                wait_for_enter()
                continue
            role = response.role
            logger.info(f"Authentication successful! Role: {role}")
            wait_for_enter()
            break
        elif opt == "2":
            username = input("Enter your username: ")
            password = input("Enter your password: ")
            bank_id = input("Enter your bank id: ")
            account_number = input("Enter your account number: ")
            register(username, password, bank_id, account_number)
        elif opt == "exit":
            logger.info("Thank you come again :)")
            exit(0)
        else:
            logger.error("Invalid input")
            wait_for_enter()
            continue

    while True:
        clear_screen()
        if role == "admin":
            print("What do you want to do? (Type exit to exit)")
            print("  1. Add client")
            print("  2. Add money")
            print()
            opt = input("Enter your choice: ").strip()
            print()
            
            if opt == "1":
                AdminAccess_create_new_client(username, password)
            elif opt == "2":
                AdminAccess_add_money()
            elif opt == "exit":
                logger.info("Thank you come again :)")
                exit(0)
            else:
                logger.error("Invalid option!")
                wait_for_enter()
        elif role == "client":
            print("What do you want to do? (Type exit to exit)")
            print("  1. Check Balance")
            print("  2. Transfer money")
            print("  3. Deposit")
            print("  4. Withdraw")
            print("  5. Get account statement")
            print()
            opt = input("Enter your choice: ").strip()
            if opt == "1":
                check_balance()
            elif opt == "2":
                receiver_username = input("Receiver's Username: ")
                receiver_bank_id = input("Receiver's Bank ID: ")
                receiver_acc_no = input("Receiver's Account Number: ")
                amount_to_be_transferred = input("Amount to be transferred: ")
                transfer_amount(receiver_username, receiver_bank_id, receiver_acc_no, amount_to_be_transferred)
            elif opt == "3":
                amount = input("Enter amount: ")
                deposit(amount)
            elif opt == "4":
                amount = input("Enter amount: ")
                withdraw(amount)
            elif opt == "5":
                get_account_statement()
            elif opt == "exit":
                logger.info("Thank you come again :)")
                exit(0)
            else:
                logger.error("Invalid option!")
                wait_for_enter()
        else:
            logger.error("Unknown error")
            wait_for_enter()

        # Printing menu
        # print("What do you want to do?")
        # print("  1. Register with payment gateway")
        # print("  2. Transfer Money")
        # print("  3. Check Balance")
        # print("  4. Add client (Admin only)")
        # print("  5. Add money (Admin only)")
        # print("  6. Exit")
        # print()

        # # Selecting option
        # option_selected = input("Enter your choice: ")
        
        # # Taking username, account number and password input (Basic info needed for all kinds of options)
        # if option_selected != "6":
        #     clear_screen()
        #     print("Your Details:\n")
        #     username = input("Enter your username: ").strip()
        #     if username == "":
        #         logger.error("Username cannot be empty")
        #         wait_for_enter()
        #         continue
        # # account_number = input("Enter your account number: ").strip()
        # # if account_number == "":
        # #     logger.error("Account Number cannot be empty")
        # #     wait_for_enter()
        # #     continue
        # # try:
        # #     account_number = int(account_number)
        # # except:
        # #     logger.error("Account number should be an integer.")
        # #     wait_for_enter()
        # #     continue
        # # if account_number < 0:
        # #     logger.error("Account number should be non-negative.")
        # #     wait_for_enter()
        # #     continue
        #     password = input("Enter your password: ")
        #     if password == "":
        #         logger.error("Password cannot be empty")
        #         wait_for_enter()
        #         continue
        #     print()
        
        # if option_selected == "1":
        #     try:
        #         bank_id = int(input("Enter your bank id: "))
        #     except:
        #         logger.error("Bank ID must be an integer")
        #         wait_for_enter()
        #         continue
        #     account_number = input("Enter your account number: ").strip()
        #     if account_number == "":
        #         logger.error("Account Number cannot be empty")
        #         wait_for_enter()
        #         continue
        #     try:
        #         account_number = int(account_number)
        #     except:
        #         logger.error("Account number should be an integer.")
        #         wait_for_enter()
        #         continue
        #     if account_number < 0:
        #         logger.error("Account number should be non-negative.")
        #         wait_for_enter()
        #         continue
        #     register(username, account_number, password, bank_id)
        # elif option_selected == "2":
        #     bank_id = input("Enter your bank id: ")
        #     check_balance(username, account_number, password)
        # elif option_selected == "3":
        #     check_balance(username, password)
        # elif option_selected == "4":
        #     new_username = input("Enter new client username: ").strip()
        #     new_password = input("Enter new client password: ")
        #     new_client_bank_id = input("Enter new client bank id: ")
        #     try:
        #         new_client_bank_id = int(new_client_bank_id)
        #     except:
        #         logger.error("Bank ID must be an integer")
        #         wait_for_enter()
        #         continue
        #     initial_balance = input("Enter initial account balance: ")
        #     try:
        #         initial_balance = float(initial_balance)
        #     except:
        #         logger.error("Initial balance should be a float")
        #         wait_for_enter()
        #         continue
        #     if initial_balance < 0:
        #         logger.error("Initial balance should be >= 0")
        #         wait_for_enter()
        #         continue
        #     AdminAccess_create_new_client(username, password, new_username, new_password, new_client_bank_id, initial_balance)
        # elif option_selected == "6":
        #     logger.info("Thank you come again :)")
        #     break
        # else:
            # logger.error("Invalid option selected.")
            # wait_for_enter()

if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="<level>{level}: {message}</level>")
    
    parser = argparse.ArgumentParser(description="Start the Client")
    parser.add_argument("--gatewayport", type=int, default=-1, help="Port on which payment gateway is listening")

    args = parser.parse_args()

    global gateway_port
    gateway_port = args.gatewayport

    ip_address = f"localhost:{gateway_port}"

    with SessionManager(ip_address):
        menu()