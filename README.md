# OSAM Docker Image for Fly.io GPU Deployment

This document describes how to use the provided `Dockerfile` to build an image for the `osam` application and deploy it to Fly.io as an HTTP service, leveraging GPU instances (like L40S).

    > [!WARNING]
    > **SECURITY WARNING:** THE `/api/generate` ENDPOINT EXPOSED BY THIS DEPLOYMENT IS **NOT SECURED** BY DEFAULT. ANYONE WITH THE URL CAN SEND REQUESTS TO IT. THIS CAN LEAD TO SIGNIFICANT GPU USAGE AND POTENTIALLY **HIGH COSTS** ON YOUR FLY.IO BILL. YOU ARE RESPONSIBLE FOR SECURING THIS ENDPOINT YOURSELF (E.G., USING AUTHENTICATION MIDDLEWARE, IP RESTRICTIONS, OR FLY.IO FEATURES LIKE PRIVATE NETWORKING IF APPLICABLE). USE AT YOUR OWN RISK.

## Docker Image

The multi-stage `Dockerfile` creates a container image with the following characteristics:

*   Based on `ubuntu:22.04`.
*   Installs the NVIDIA apt repository and required CUDA runtime libraries (`libcublas-12-2`, `libcudnn8`) needed by ONNX Runtime for GPU execution. *Note: Drivers are provided by the Fly.io host environment.*
*   Installs Git, Python 3, and `uv`.
*   **Installs `osam` directly from the [jumasheff/osam fork](https://github.com/jumasheff/osam.git) using `uv pip install "git+https://github.com/jumasheff/osam.git#egg=osam[serve]"`.** This fork includes necessary server components. The `Dockerfile` does *not* clone the repository separately.
*   Sets up a virtual environment (`/venv`) for dependencies.
*   Sets the default `CMD` to run the `uvicorn` server directly, binding to `0.0.0.0:11368`: `["/venv/bin/uvicorn", "osam._server:app", "--host", "0.0.0.0", "--port", "11368"]`. This makes the container primarily suitable for running the web service via `fly deploy`.

## Fly.io GPU Deployment (HTTP Service)

**Prerequisites:**

*   A Fly.io account with GPU access enabled for your organization.
*   [flyctl](https://fly.io/docs/hands-on/install-flyctl/) installed and authenticated (`fly auth login`).

**Available GPUs & Regions (as per docs):**

*   `a10`: `ord`
*   `l40s`: `ord`
*   `a100-40gb` (a100-pcie-40gb): `ord`
*   `a100-80gb` (a100-sxm4-80gb): `iad`, `sjc`, `syd`

Choose a region that offers the GPU type you need (e.g., `ord` for `l40s`).

**Deployment Approach: On-Demand Service via `fly deploy`**

This method deploys the app persistently using the `fly.toml` configuration. It's configured to shut down when idle (`min_machines_running = 0`, `auto_stop_machines = 'stop'`) and start automatically when an HTTP request arrives.

**Steps:**

1.  **Prepare `fly.toml`:**
    Copy the example configuration file:
    ```bash
    cp fly.toml.example fly.toml
    ```
    *(Note: Before deploying, you must first create the app on Fly.io if it doesn't exist. You can do this using `fly apps create your-osam-app-name` or by running `fly launch`. `fly launch` will detect `fly.toml` and prompt you to create the app based on its configuration. Ensure your `fly.toml` has the correct GPU `[[vm]]` size, `[[mounts]]`, and `[http_service]` settings before creating the app.)*

    Now, edit the `fly.toml` file. Ensure it looks similar to this, adjusted for your application name and desired settings:

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
      size = 'l40s' # Specify the GPU VM size preset (e.g., a10, a100-40gb)
    ```

    *   **Crucially, change the `app` name to something unique.**
    *   Adjust `primary_region`, `vm.size`, `initial_size` as needed.
    *   Using `force_https = true` is recommended for production but commented out by default here.

2.  **Deploy the App:**
    Run the deployment command from the directory containing your `Dockerfile` and `fly.toml`:
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
        See the `send_request_example.py` file for a complete example of how to send requests to the API using Python. You'll need to update the `API_ENDPOINT` to point to your Fly.io app URL (`https://<your-app-name>.fly.dev`).

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

*   Implement authentication/authorization for the `/api/generate` endpoint. This could potentially be added:
    *   Directly within the `osam` project (ideal).
    *   As middleware configured via this repository's setup (e.g., modifying the `CMD` or adding a proxy).
    *   Leveraging Fly.io platform features if suitable for the use case (e.g., private network access).
