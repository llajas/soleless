REGISTRY ?= "registry.lajas.tech"
REPO ?= "soleless-app"
TAG ?= $(shell get describe --tags --always --dirty)
IMG ?= $(REGISTRY)/$(REPO):$(TAG)

.PHONY: build
build:
  docker build -t $(IMG) .

.PHONY: push
push:
  docker push $(IMG)
