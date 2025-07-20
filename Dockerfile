FROM python:3.11-slim
WORKDIR /usr/src/app
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app /usr/src/app/app
COPY gunicorn_conf.py .
EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn_conf.py", "app.main:app"]
