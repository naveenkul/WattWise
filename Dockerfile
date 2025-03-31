FROM python:3.10-slim

WORKDIR /app

COPY README.md LICENSE pyproject.toml setup.py ./
COPY wattwise ./wattwise

RUN pip install --no-cache-dir .

RUN mkdir -p /root/.config/wattwise
RUN mkdir -p /root/.local/share/wattwise

# Set the entrypoint to the wattwise command
ENTRYPOINT ["wattwise"]

CMD [] 
