# OSAM Docker Image for Fly.io GPU Deployment

This document describes how to use the provided `Dockerfile` to build an image for the `osam` application and deploy it to Fly.io as an HTTP service, leveraging GPU instances (like L40S).

## Docker Image

The multi-stage `Dockerfile` creates a container image with the following characteristics:

*   Based on `ubuntu:22.04`.
*   Installs the NVIDIA apt repository and required CUDA runtime libraries (`libcublas-12-2`, `libcudnn8`) needed by ONNX Runtime for GPU execution. *Note: Drivers are provided by the Fly.io host environment.*
*   Installs Git, Python 3, and `uv`.
*   Clones the `osam` repository (default: `https://github.com/wkentaro/osam.git`, configurable via `--build-arg REPO_URL`). It's recommended to clone a specific tag/commit for production builds.
*   Installs Python dependencies from `pyproject.toml` (including optional `serve` dependencies) into a virtual environment (`/opt/venv`) using `uv pip install --locked`.
*   **Does NOT set an `ENTRYPOINT`.**
*   Sets the default `CMD` to run the `uvicorn` server directly, binding to `0.0.0.0:11368`: `["uvicorn", "osam._server:app", "--host", "0.0.0.0", "--port", "11368"]`. This makes the container primarily suitable for running the web service via `fly deploy`.

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

This method deploys the app persistently using the `fly.toml` configuration. It's configured to shut down when idle (`min_machines_running = 0`, `auto_stop_machines = true`) and start automatically when an HTTP request arrives.

**Steps:**

1.  **Create `fly.toml`:**
    Ensure you have a `fly.toml` file in your deployment directory (where the `Dockerfile` is). It should look similar to this, adjusted for your application name and desired settings:

    ```toml
    # fly.toml
    app = "chalkanosam" # Your Fly app name
    primary_region = "ord"    # Desired region with GPUs (e.g., ord for l40s)

    [[vm]]
      size = 'l40s' # Specify the GPU VM size preset (e.g., a10, a100-40gb)

    # Define where to build from
    [build]
      dockerfile = "Dockerfile"
      # Or uncomment below to build from local Dockerfile on deploy:
      # build-target = "runtime" # Specify the final stage if using multi-stage target
      # [build.args]
      #   REPO_URL = "https://github.com/wkentaro/osam.git"

    # Define the volume mount for the model cache
    # Fly deploy will automatically create this volume if it doesn't exist
    [[mounts]]
      source = "osam_cache"
      destination = "/root/.cache/osam"
      initial_size = "5gb" # Adjust size based on expected model usage

    # Define the HTTP service configuration
    [http_service]
      internal_port = 11368 # Matches the port in Dockerfile CMD
      force_https = true # Recommended: Enforce HTTPS
      auto_stop_machines = true # Stop machine when idle
      auto_start_machines = true # Start machine on new requests
      min_machines_running = 0 # Allow machine to scale to zero
      processes = ["app"] # Uses the default process group run by CMD
    ```

    *   Replace placeholder values (like `app` name) if necessary.
    *   Adjust `primary_region`, `vm.size`, `initial_size` as needed.
    *   This configuration tells Fly.io to build using the local `Dockerfile`, mount a volume for caching, and run an HTTP service that listens internally on `11368`. Because there is no `[processes]` section, Fly uses the `Dockerfile`'s `CMD` to start the service.

2.  **Deploy the App:**
    This command creates the app (if it doesn't exist), creates the volume (if it doesn't exist and is defined in `fly.toml`), builds the Docker image, pushes it, and starts the machine(s) based on the config.
    ```bash
    fly deploy
    ```

3.  **Interact with the Service:**
    Once deployed, your service will be available at `https://<your-app-name>.fly.dev`. You can send POST requests to the `/api/generate` endpoint.

    *   **Get App Hostname:**
        ```bash
        APP_HOSTNAME=$(fly status --app chalkanosam --json | jq -r .Hostname)
        echo "App available at: https://${APP_HOSTNAME}"
        ```
    *   **Example `curl` Request (assuming `examples/_images/dogs.jpg` is local):**
        ```bash
        curl "https://${APP_HOSTNAME}/api/generate" -X POST \\
          -H "Content-Type: application/json" \\
          -d "{\\"model\\": \\"efficientsam\\", \\"image\\": \\"$(cat examples/_images/dogs.jpg | base64)\\"}" \\
          | jq -r .mask | base64 --decode > fly_mask.png
        ```

    *   **Using `fly ssh console` (for debugging):**
        You can still SSH into the running machine for debugging:
        ```bash
        fly ssh console
        ```
        However, since there's no `ENTRYPOINT` configured for the `osam` CLI, you need to use the full path to run `osam` commands inside the shell:
        ```bash
        # Inside the SSH console
        /opt/venv/bin/osam --help
        /opt/venv/bin/osam run sam2:large --image /root/.cache/osam/path/to/image.jpg ...
        ```

## General Notes

*   **Model Downloads:** The first time you make an API request for a specific model (e.g., `efficientsam`, `sam2:large`), `osam` (via the server) will download it into the `/root/.cache/osam` directory, which resides on your persistent volume. Subsequent requests for the same model will reuse the cached version.
*   **Cold Starts:** With `auto_stop_machines = true` and `min_machines_running = 0`, the first request after a period of inactivity might take longer as the machine needs to start up.
*   **Error Handling:** Check logs using `fly logs -a <your-app-name>`.
*   **Memory:** Monitor system RAM and GPU VRAM usage (`fly ssh console` then `top`, `nvidia-smi`). Large models might require larger VM presets (`vm.size` in `fly.toml`). If you encounter CUDA memory allocation errors, you might need to add environment variables. This can be done by adding a `[env]` section to your `fly.toml`:
    ```toml
    [env]
      PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
    ```

## Alternative: One-off Tasks (`fly machine run`)

While the primary goal is serving, you *could* still run one-off `osam` commands using `fly machine run`. However, because the `Dockerfile` has no `osam` `ENTRYPOINT` defined by default, the command is more complex:

```bash
# Example: Run sam2:large on a specific image already on the volume
fly machine run . \\
  --app chalkanosam \\
  --region ord \\
  --gpu-kind l40s \\
  --vm-size l40s \\
  --volume osam_cache:/root/.cache/osam \\
  --env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \\
  --entrypoint /bin/bash -- /opt/venv/bin/osam run sam2:large \\
    --image /root/.cache/osam/path/to/your/image.jpg \\
    --prompt '{\\"texts\\": [\\"your prompt text\\"]}'
```
*Note the need to explicitly set `--entrypoint /bin/bash` and provide the full path to the `osam` executable.* This is generally less convenient than the `fly deploy` approach for a persistent service.

## Additional Note

We are using `osam`'s fork in the Dockerfile: `uv pip install "git+https://github.com/jumasheff/osam.git#egg=osam[serve]"`.
After it gets merged, we can use the package installation instead: `pip install "osam[serve]"`# osam-on-fly
