"""Interactive NASA Earthdata login. YOU type your username and password
(the password is hidden); earthaccess saves them to ~/.netrc so the pipeline
can download NISAR. Create a free account at https://urs.earthdata.nasa.gov first."""
import earthaccess

print("\nNASA Earthdata login (account: https://urs.earthdata.nasa.gov)")
auth = earthaccess.login(strategy="interactive", persist=True)
print("\nLogin OK and saved to ~/.netrc" if auth.authenticated else "\nLogin FAILED - check username/password")
