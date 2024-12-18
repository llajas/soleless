REGISTRY ?= "registry.lajas.tech"
REPO ?= "soleless-app"
TAG ?= $(shell git describe --tags --always --dirty)
IMG ?= $(REGISTRY)/$(REPO):$(TAG)

all: build push
.PHONY: all

.PHONY: build
build:
  docker build -t $(IMG) . -f Containerfile

.PHONY: push
push:
  docker push $(IMG)
