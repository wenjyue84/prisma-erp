#!/bin/bash
curl -s http://localhost:8080/login | grep -o 'login.bundle[^"]*css\|website.bundle[^"]*css\|lms.bundle[^"]*css' | head -10
