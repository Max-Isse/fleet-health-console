# Included in every location: nginx drops server-level add_header lines in any location that sets its own.
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://localhost:8080; frame-src http://localhost:8080; frame-ancestors 'none'; base-uri 'self'; form-action 'self' http://localhost:8080" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
