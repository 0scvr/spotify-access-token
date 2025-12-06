import argparse
import hashlib
import base64
import secrets
import urllib.parse
import requests
import pyperclip
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configuration
REDIRECT_URI = 'http://127.0.0.1:8888/callback'
SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'

class RequestHandler(BaseHTTPRequestHandler):
    """
    Temporary local server to capture the authorization code.
    """
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.server.state = params.get('state', [None])[0]
            
            # Send a nice response to the browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><h1>Authorization Successful</h1><p>You can close this window and return to your terminal.</p></html>")
        elif 'error' in params:
            self.send_response(400)
            self.wfile.write(b"Authorization failed.")
            self.server.auth_code = None
        
def generate_pkce_pair():
    """Generates a code verifier and code challenge."""
    # 1. Generate a high-entropy random string (Code Verifier)
    code_verifier = secrets.token_urlsafe(64)
    
    # 2. Hash it with SHA256
    digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    
    # 3. Base64 URL-encode the hash (Code Challenge)
    # python's urlsafe_b64encode adds padding '=', which PKCE spec requires removing
    code_challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
    
    return code_verifier, code_challenge

def get_access_token(client_id, client_secret, scope):
    # 1. Generate PKCE Data
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    # 2. Start Local Server
    server = HTTPServer(('localhost', 8888), RequestHandler)
    print(f"[*] Local server started at {REDIRECT_URI}")
    
    # 3. Construct Auth URL
    params = {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'code_challenge_method': 'S256',
        'code_challenge': challenge,
        'scope': scope,
        'state': state
    }
    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    print(f"[*] Open browser and navigate to this URL to authorize...")
    print(f"    URL: {auth_url}")
    pyperclip.copy(auth_url)
    print(f"[-] Authorization URL copied to clipboard.")

    # 4. Wait for Callback (handle_request handles a single request then returns)
    print("[*] Waiting for user authorization...")
    server.handle_request()
    
    if not hasattr(server, 'auth_code') or not server.auth_code:
        print("[!] Authorization failed or cancelled.")
        return

    print("[*] Authorization code received.")

    # 5. Exchange Code for Token
    print("[*] Exchanging code for access token...")
    
    data = {
        'grant_type': 'authorization_code',
        'code': server.auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': client_id,
        'code_verifier': verifier,
    }

    headers = {}
    
    # If client_secret is provided, we use Basic Auth (Confidential Client flow)
    # If not, we omit it (Public Client flow with PKCE)
    if client_secret:
        auth_str = f"{client_id}:{client_secret}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        headers['Authorization'] = f"Basic {b64_auth}"
    
    response = requests.post(SPOTIFY_TOKEN_URL, data=data, headers=headers)
    
    if response.status_code == 200:
        token_info = response.json()
        print("\n" + "="*60)
        print("SUCCESS! HERE IS YOUR TOKEN DATA")
        print("="*60)
        print(f"\nAccess Token:\n{token_info['access_token']}\n")
        if 'refresh_token' in token_info:
            print(f"Refresh Token (Keep this safe!):\n{token_info['refresh_token']}\n")
        print(f"Expires in: {token_info['expires_in']} seconds")
        print("="*60)
        pyperclip.copy(token_info['access_token'])
        print(f"[-] Access token copied to clipboard.")
    else:
        print(f"\n[!] Error fetching token: {response.status_code}")
        print(response.json())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get Spotify Access Token via PKCE')
    parser.add_argument('--client_id', required=True, help='Spotify Client ID')
    parser.add_argument('--client_secret', required=False, default='', help='Spotify Client Secret')
    parser.add_argument('--scope', default='user-read-private user-library-read playlist-read-private playlist-read-collaborative', help='Space separated scopes')
    
    args = parser.parse_args()
    
    get_access_token(args.client_id, args.client_secret, args.scope)