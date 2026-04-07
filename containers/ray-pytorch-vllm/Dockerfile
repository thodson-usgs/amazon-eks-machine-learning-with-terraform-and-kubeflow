FROM rayproject/ray:2.54.1-py312-cu128

# Combine environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    DEBCONF_NONINTERACTIVE_SEEN=true \
    PYTHONUNBUFFERED=1

USER root
# Install build dependencies for flash-attn (ninja helps speed up compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

USER ray
# Upgrade pip and install heavy dependencies in one layer
# Using --no-cache-dir keeps the image size down
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        vllm==0.19.0 \
        pandas==3.0.2 \
        pyarrow==23.0.1 \
        scipy==1.17.1

RUN pip install --no-cache-dir transformers==5.5.0

CMD ["/bin/bash"]
