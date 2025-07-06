PROTO_DIR=proto
OUT_DIR=generated
PAYMENT_GATEWAY_PORT=50051
DEFAULT_PORT=50052

# Allow overriding port and ID from the command line
PORT ?= $(DEFAULT_PORT)

# Find all .proto files in the proto directory
PROTO_FILES=$(wildcard $(PROTO_DIR)/*.proto)
GENERATED_FILES=$(PROTO_FILES:$(PROTO_DIR)/%.proto=$(OUT_DIR)/%_pb2.py)

all: compile

compile: $(GENERATED_FILES)

$(OUT_DIR)/%_pb2.py: $(PROTO_DIR)/%.proto
	pip3 install -r requirements.txt
	python3 -m grpc_tools.protoc --proto_path=$(PROTO_DIR) --python_out=$(OUT_DIR) --grpc_python_out=$(OUT_DIR) $<

bank_server:
	python3 server/bank_server.py --port=$(PORT) --gatewayport=$(PAYMENT_GATEWAY_PORT)

run_client:
	python3 client/client.py --gatewayport=$(PAYMENT_GATEWAY_PORT)

payment_gateway:
	python3 server/payment_gateway.py --port=$(PAYMENT_GATEWAY_PORT)

clean:
	rm -rf $(OUT_DIR)/*_pb2.py*
	rm -rf $(OUT_DIR)/*_pb2_grpc.py*
	find . -name "__pycache__" -type d -exec rm -rf {} +