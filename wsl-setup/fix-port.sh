#!/bin/bash
sed -i 's/--port 8000/--port 8080/' ~/frappe-bench/Procfile
grep port ~/frappe-bench/Procfile
