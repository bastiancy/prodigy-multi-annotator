FROM python:3.6-slim

RUN apt-get update && apt-get install -y build-essential python-dev openssl less curl

RUN mkdir -p /tmp/lib
COPY ./requirements.txt /tmp/lib
COPY ./*.whl /tmp/lib

RUN curl https://bootstrap.pypa.io/get-pip.py | python3
RUN pip3 install --no-cache-dir -r /tmp/lib/requirements.txt
RUN pip3 install /tmp/lib/prodigy-1.5*.whl
RUN python3 -m spacy download en

WORKDIR /app

EXPOSE 8080
EXPOSE 6000
