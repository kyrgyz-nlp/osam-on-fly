# OSAM Docker Image for Fly.io GPU Deployment

This document describes how to use the provided [`Dockerfile`](./Dockerfile) to build an image for the [`osam`](https://github.com/wkentaro/osam) application and deploy it to [Fly.io](https://fly.io) as an HTTP service, leveraging GPU instances (like L40S).

_SECURITY: This deployment now uses API Key Authentication (via the `X-API-Key` header) to protect the `/api/generate` endpoint.
You MUST configure a strong, secret `API_KEY` (using `fly secrets set API_KEY=...` for Fly.io or the `.env` file for local runs) to prevent unauthorized access.
Failure to secure the endpoint can lead to significant GPU usage and potentially high costs on your Fly.io bill.
See the "Security: API Key Authentication" section below for setup details._

## Docker Image

The multi-stage [`Dockerfile`](./Dockerfile) creates a container image with the following characteristics:

*   Based on `ubuntu:22.04`.
*   Installs the NVIDIA apt repository and required CUDA runtime libraries (`libcublas-12-2`, `libcudnn8`) needed by ONNX Runtime for GPU execution. *Note: Drivers are provided by the Fly.io host environment.*
*   Installs Git, Python 3, and `uv`.
*   Installs `osam` directly from the [jumasheff/osam fork](https://github.com/jumasheff/osam.git) using `uv pip install "git+https://github.com/jumasheff/osam.git#egg=osam[serve]"`. This fork includes necessary fixes. The [`Dockerfile`](./Dockerfile) does *not* clone the repository separately. When this fork is merged into the main repository, the Dockerfile will be updated to use `pip install osam[serve]` directly.
*   Sets up a virtual environment (`/venv`) for dependencies.
*   Sets the default `CMD` to run the `uvicorn` server via the [`main:app`](./main.py) wrapper (which adds API key security), binding to `0.0.0.0:11368`: `["/venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "11368"]`. This makes the container primarily suitable for running the web service via `fly deploy`.

## Fly.io GPU Deployment (HTTP Service)

**Prerequisites:**

*   A Fly.io account with GPU access enabled for your organization.
*   [`flyctl`](https://fly.io/docs/hands-on/install-flyctl/) installed and authenticated (`fly auth login`).

**Available GPUs & Regions (as per [docs](https://fly.io/docs/gpus/gpu-quickstart/)):**

*   `a10`: `ord`
*   `l40s`: `ord`
*   `a100-40gb` (a100-pcie-40gb): `ord`
*   `a100-80gb` (a100-sxm4-80gb): `iad`, `sjc`, `syd`

Choose a region that offers the GPU type you need (e.g., `ord` for `l40s`).

**Deployment Approach: On-Demand Service via `fly deploy`**

This method deploys the app persistently using the [`fly.toml`](./fly.toml.example) configuration. It's configured to shut down when idle (`min_machines_running = 0`, `auto_stop_machines = 'stop'`) and start automatically when an HTTP request arrives.

**Steps:**

1.  **Prepare [`fly.toml`](./fly.toml):**
    Copy the example configuration file:
    ```bash
    cp fly.toml.example fly.toml
    ```
    *(Note: Before deploying, you must first create the app on Fly.io if it doesn't exist. You can do this using `fly apps create your-osam-app-name` or by running `fly launch`. `fly launch` will detect [`fly.toml`](./fly.toml) and prompt you to create the app based on its configuration. Ensure your [`fly.toml`](./fly.toml) has the correct GPU `[[vm]]` size, `[[mounts]]`, and `[http_service]` settings before creating the app.)*

    Now, edit the [`fly.toml`](./fly.toml) file. Ensure it looks similar to this, adjusted for your application name and desired settings:

    ```toml
    # fly.toml
    app = "your-osam-app-name" # !!! CHANGE THIS to your unique Fly app name !!!
    primary_region = "ord"    # Desired region with GPUs (e.g., ord for l40s)

    # Define where to build from
    [build]
      dockerfile = "Dockerfile"
      # The Dockerfile installs osam directly, no need for build args here normally.

    # Define the volume mount for the model cache
    # Fly deploy will automatically create this volume if it doesn't exist
    [[mounts]]
      source = "osam_cache"
      destination = "/root/.cache/osam"
      initial_size = "5gb" # Adjust size based on expected model usage

    # Define the HTTP service configuration
    [http_service]
      internal_port = 11368 # Matches the port in Dockerfile CMD
      # force_https = true # Recommended: Enforce HTTPS (uncomment if needed)
      auto_stop_machines = 'stop' # Stop machine when idle (uses string value like fly.toml.example)
      auto_start_machines = true # Start machine on new requests
      min_machines_running = 0 # Allow machine to scale to zero
      processes = ["app"] # Uses the default process group run by CMD

    # Define the VM size (GPU type)
    [[vm]]
      size = 'l40s' # Specify the GPU VM size preset (e.g., [a10, a100-40gb](https://fly.io/docs/gpus/gpu-quickstart/))
    ```

    *   **Crucially, change the `app` name to something unique.**
    *   Adjust `primary_region`, `vm.size`, `initial_size` as needed.
    *   Using `force_https = true` is recommended for production but commented out by default here.

2.  **Deploy the App:**
    Run the deployment command from the directory containing your [`Dockerfile`](./Dockerfile) and [`fly.toml`](./fly.toml):
    ```bash
    fly deploy
    ```
    *Note: You must have already created the Fly.io app (using `fly apps create` or `fly launch`) before running `fly deploy`. However, `fly deploy` *will* automatically create the volume defined in `[[mounts]]` during the first deployment if it doesn't exist.*

3.  **Interact with the Service:**
    Once deployed, your service will be available at `https://<your-app-name>.fly.dev`. You can send POST requests to the `/api/generate` endpoint.

    *   **Get App Hostname:**
        ```bash
        # Replace 'your-osam-app-name' with the actual app name from your fly.toml
        APP_NAME="your-osam-app-name"
        APP_HOSTNAME=$(fly status --app $APP_NAME --json | jq -r .Hostname)
        echo "App available at: https://${APP_HOSTNAME}"
        ```
    *   **Example Python Request:**
        See the [`send_request_example.py`](./send_request_example.py) file for a complete example of how to send requests to the API using Python. You'll need to update the `API_ENDPOINT` to point to your Fly.io app URL (`https://<your-app-name>.fly.dev`).

    *   **Using `fly ssh console` (for debugging):**
        You can SSH into the running machine for debugging:
        ```bash
        fly ssh console -a <your-app-name>
        ```

## General Notes

*   **Model Downloads:** The first time you make an API request for a specific model (e.g., `efficientsam`, `sam2:large`), `osam` (via the server) will download it into the `/root/.cache/osam` directory, which resides on your persistent volume. Subsequent requests for the same model will reuse the cached version.
*   **Cold Starts:** With `auto_stop_machines = 'stop'` and `min_machines_running = 0`, the first request after a period of inactivity might take longer as the machine needs to start up.
*   **Error Handling:** Check logs using `fly logs -a <your-app-name>`.

## TODO: Security

*   Consider proposing the API key security wrapper mechanism implemented here as an enhancement to the upstream `osam` project.

## Security: API Key Authentication

This deployment now includes a simple API key authentication mechanism to protect the `/api/generate` endpoint.

The [`main.py`](./main.py) script acts as a wrapper around the original `osam._server:app`. It requires an API key to be sent in the `X-API-Key` header for all incoming requests.

### Setting the API Key

How you set the required `API_KEY` depends on your environment:

*   **Fly.io Deployment:**
    Use the `fly secrets set` command. This is the **recommended method for production**. Secrets set via `fly secrets` take precedence over environment variables defined elsewhere (like [`.env`](./.env)).
    ```bash
    fly secrets set API_KEY=YOUR_SUPER_SECRET_KEY -a your-osam-app-name
    ```
    Replace `YOUR_SUPER_SECRET_KEY` with a strong, unique key and `your-osam-app-name` with your app's name.

*   **Local Development (outside Fly.io):**

    **Design Decision:** We do **not** copy the [`.env`](./.env) file directly into the Docker image during the build process ([`Dockerfile`](./Dockerfile) has no `COPY .env ...`). Embedding secrets like API keys directly into container images is insecure, as the image might be shared or stored in registries where the secrets could be exposed.

    Instead, we use standard Docker methods to inject these settings when running the container locally:

    1.  **Create/Update [`.env`](./.env) file:** If it doesn't exist, copy the example: `cp .env.example .env`. Edit the [`.env`](./.env) file to set your desired `API_KEY` and optionally `APP_ENV=development`.
        ```dotenv
        # .env file contents
        API_KEY=your_local_key_here
        APP_ENV=development
        ```
    2.  **Important:** Ensure [`.env`](./.env) is listed in your [`.gitignore`](./.gitignore) file to prevent accidentally committing secrets.
    3.  **Run the container with `--env-file`:** When you run the container locally using `docker run`, use the `--env-file` flag to load the variables from your [`.env`](./.env) file directly into the container's environment:
        ```bash
        # Assuming you have built the image (e.g., docker build -t my-osam-app .)
        docker run --rm -p 11368:11368 --env-file ./.env my-osam-app
        ```
        The [`main.py`](./main.py) script within the container will then read these environment variables using `os.environ.get()`. 

        **Role of `load_dotenv()` in [`main.py`](./main.py):** The `load_dotenv()` call present in [`main.py`](./main.py) is primarily designed to facilitate running the script *directly* on your host machine (e.g., for quick tests via `python main.py`). In that scenario, it *will* load variables from a [`.env`](./.env) file in the same directory. However, when running inside a Docker container using the `--env-file` method described above, the variables are already injected into the environment *before* the Python script starts, making the `load_dotenv()` call less critical (though harmless).

### Development vs. Production Mode (`APP_ENV`)

By default, the application runs in "production" mode, meaning the `API_KEY` **must** be set (either via `fly secrets set` command or manually through the Fly dashboard), and requests without a valid `X-API-Key` header will be rejected with a 401 Unauthorized response.

For local development, you can optionally set the `APP_ENV` environment variable to `development`:

*   Add `APP_ENV=development` to your [`.env`](./.env) file.
*   Or set it when running the container: `docker run -e APP_ENV=development ...`

In `development` mode, if the `API_KEY` is *not* set, authentication will be bypassed, and a warning will be printed to the console. This allows easier testing without needing a key configured, but **should not be used in production.**

### Client Usage

See [`send_request_example.py`](./send_request_example.py) for a complete working example


Clients interacting with the deployed service must include the API key in the `X-API-Key` header:

```python
import requests
import base64
import os

api_key = os.environ.get("API_KEY") # Get key from environment variable
if not api_key:
    raise ValueError("osam `API_KEY` environment variable not set.")

# Use your deployed app URL or localhost for local testing
app_url = "https://your-osam-app-name.fly.dev"
# Or for local testing: app_url = "http://localhost:11368"

image_path = "examples/_images/dogs.jpg" # Path to your image

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

# Read image, encode to base64
try:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
except FileNotFoundError:
    print(f"Error: Image file not found at {image_path}")
    exit()
except Exception as e:
    print(f"Error reading or encoding image: {e}")
    exit()


data = {
    "model": "efficientsam", # Or "sam2:tiny", etc.
    "image": image_base64,
    "prompt": {
        # Example prompt for dogs.jpg (adjust points as needed)
        "points": [[1439, 504], [1439, 1289]],
        "point_labels": [1, 1] # 1 indicates foreground points
    }
}

print(f"Sending request to {app_url}/api/generate...")
response = requests.post(f"{app_url}/api/generate", headers=headers, json=data)

if response.status_code == 200:
    result = response.json()
    print("Success! Response keys:", result.keys())
    # Process the result, e.g., save the mask
elif response.status_code == 403:
    print("Authentication Error (403):", response.json())
    print("Ensure the correct API key is set in API_KEY environment variable and matches the server's API_KEY.")
elif response.status_code == 422:
     print(f"Validation Error ({response.status_code}): Check your payload.")
     try:
         print(response.json())
     except requests.exceptions.JSONDecodeError:
         print(response.text)
elif response.status_code == 500:
    print("Server Error (500):", response.text)
    print("Check server logs (`fly logs`) and ensure the API_KEY secret is correctly set on Fly.io.")
else:
    print("Error:", response.status_code, response.text)

```
