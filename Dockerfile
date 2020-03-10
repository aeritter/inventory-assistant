FROM python:3.8.2
WORKDIR /usr/src/app
COPY requirements.txt ./
VOLUME /usr/src/app/network-share
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD [ "python", "-u", "./airtable-import.py"]