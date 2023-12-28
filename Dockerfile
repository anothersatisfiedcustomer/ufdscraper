FROM python:3-slim

WORKDIR /app
COPY ufdscraper /app/ufdscraper
CMD python ufdscraper/ufdscraper.py --start "$START_DATE" --end "$END_DATE" --dump-to-file $EXTRA_ARGUMENTS