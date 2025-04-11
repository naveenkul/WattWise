FROM python:3.10-slim

WORKDIR /app

COPY README.md LICENSE pyproject.toml setup.py ./
COPY wattwise ./wattwise

RUN pip install --no-cache-dir python-kasa>=0.10.2

RUN pip install --no-cache-dir .

# Create directories with correct permissions
RUN mkdir -p /root/.config/wattwise && \
    mkdir -p /root/.local/share/wattwise && \
    chmod -R 755 /root/.config/wattwise && \
    chmod -R 755 /root/.local/share/wattwise

# Set the entrypoint to the wattwise command
ENTRYPOINT ["wattwise"]

CMD [] 
