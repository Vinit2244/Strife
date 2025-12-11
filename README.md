# 🏦 Secure Banking System with Payment Gateway

[![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)
[![gRPC](https://img.shields.io/badge/gRPC-Protocol%20Buffers-blue)](https://grpc.io/)
[![security](https://img.shields.io/badge/Security-SSL%2FTLS-green)](https://www.openssl.org/)

A distributed banking system that uses gRPC for communication between clients, a payment gateway, and multiple bank servers. The system includes secure authentication and transaction mechanisms.

## 📋 Features

- ✅ Multi-bank architecture with a centralized payment gateway
- ✅ Secure client authentication with username/password
- ✅ Admin interface for account management
- ✅ Inter-bank fund transfers
- ✅ Account balance queries
- ✅ SSL/TLS encryption support for secure communication
- ✅ Unique client identification with error handling
- ✅ Persistent session management for clients

## 🛠️ Requirements

```
grpcio
grpcio-tools
loguru
```

## 🚀 Getting Started

### Step 1: Compile Protocol Buffers

```bash
make compile
# or simply
make
```

### Step 2: Start the Payment Gateway

```bash
make payment_gateway
```

The payment gateway will run on the default port 50051.

### Step 3: Start One or More Bank Servers

```bash
make bank_server PORT=50052
```

You can start multiple bank servers with different IDs and ports.

### Step 4: Run a Client

```bash
make run_client
```

## 🔐 Security Features

The system includes SSL/TLS support with custom certificates. The repository includes a Certificate Authority (CA) setup for generating and signing certificates.

### CA Certificate Generation

```bash
# Inside CA folder
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 -out ca.crt
```

### Server Certificate Generation

```bash
# Create server key and CSR
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -config server.cnf

# Get CSR signed by CA
openssl x509 -req -in server.csr -CA ../CA/ca.crt -CAkey ../CA/ca.key \
  -CAcreateserial -out server.crt -days 365 -sha256 -extfile server.cnf -extensions req_ext
```

## 🔍 System Assumptions

- Each bank has a unique ID and clients refer to banks by their IDs
- The admin user has the account number 0, username "admin", and password "1234"
- Each user has a unique username across the system
- A user can have only one account in any one bank
- Banks are assumed to be persistent (once started, they don't go down)
- New clients must register with the payment gateway after account creation
- Payment gateway opens channels with banks on a per-request basis for efficiency
- Client sessions remain open until termination to avoid repeated authentication

## 🏛️ Architecture

```
┌─────────┐     ┌───────────────────┐     ┌────────────┐
│ Client 1│────▶   Payment Gateway  │────▶│ Bank 1     │
└─────────┘     │                   │     └────────────┘
                │  - Authentication │      
┌─────────┐     │  - Routing        │     ┌────────────┐
│ Client 2│────▶   - Security       │────▶│ Bank 2     │
└─────────┘     │  - Admin          │     └────────────┘
                │   Functions       │      
┌─────────┐     │                   │     ┌────────────┐
│ Admin   │────▶                    │────▶│ Bank 3     │
└─────────┘     └───────────────────┘     └────────────┘
```

## 📝 Implementation Notes

- Payment gateway serves as the central hub for all client-bank interactions
- Admin user can create new accounts for clients
- Security checks are applied at both Bank and Payment Gateway levels
- When transferring funds, complete receiver information is required to ensure accuracy
- The system uses gRPC for efficient, typed communication between components

## 🤝 Credits

Created as part of a Distributed Systems assignment at IIIT Hyderabad.

## 📚 References

Original implementation prompts:
- [ChatGPT Prompt 1](https://chatgpt.com/share/67cc4469-dec4-8007-8f77-d5d0e46eaeb3)
- [Claude Prompt 2](https://claude.ai/share/6bd30c4b-d2dd-4f79-8957-d4a863aea01d)
