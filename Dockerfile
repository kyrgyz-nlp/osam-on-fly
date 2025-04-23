# Stage 1: Base with NVIDIA repo setup
FROM ubuntu:22.04 as base
ARG DEBIAN_FRONTEND=noninteractive
# Install prerequisites and NVIDIA keyring
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    gnupg \
 && wget -qO /cuda-keyring.deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb \
 && dpkg -i /cuda-keyring.deb \
 && rm /cuda-keyring.deb \
 && apt-get update \
 && rm -rf /var/lib/apt/lists/*

# Stage 2: Builder with Git, Python, uv, and dependencies
FROM base as builder
ARG DEBIAN_FRONTEND=noninteractive
# Install Git, Python, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3.10 \
    python3-pip \
    python3.10-dev \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copy uv binary from the official astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set workdir
WORKDIR /app

# Set environment variable for uv to use /venv as the virtual environment
ENV UV_PROJECT_ENVIRONMENT=/venv
ENV UV_PYTHON=/usr/bin/python3.10

# Create the virtual environment and install packages
RUN uv venv /venv --python $UV_PYTHON \
    && . /venv/bin/activate \
    && UV_PYTHON=/venv/bin/python uv pip install "git+https://github.com/jumasheff/osam.git#egg=osam[serve]"

# Stage 3: Final runtime image
FROM base as runtime
ARG DEBIAN_FRONTEND=noninteractive
# Install Python runtime and required NVIDIA runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    libcublas-12-2 \
    libcudnn8 \
 && rm -rf /var/lib/apt/lists/*

# Copy uv binary to runtime image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables for runtime
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV UV_PROJECT_ENVIRONMENT=/venv
ENV UV_PYTHON=/usr/bin/python3.10

# Set the working directory for the runtime
WORKDIR /app

# Copy virtual environment from the builder stage
COPY --from=builder /venv /venv

# Expose the server port
EXPOSE 11368

# Use the virtual environment's Python and run uvicorn directly
CMD ["/venv/bin/uvicorn", "osam._server:app", "--host", "0.0.0.0", "--port", "11368"]