"""Smoke test: verify CDS API credentials in ~/.cdsapirc authenticate correctly.

Instantiates a cdsapi.Client(), which reads ~/.cdsapirc and validates the
personal access token against the CDS API. Does not download any data.
"""
import cdsapi


def main() -> None:
    print("Initialising cdsapi.Client() (reads ~/.cdsapirc)...")
    client = cdsapi.Client()
    print("Client initialised.")
    print(f"  url: {client.url}")
    print(f"  key: {client.key[:8]}... (masked)")

    # Hit an authenticated endpoint to confirm the token is accepted.
    # client.client is the underlying datapi session in cdsapi >= 0.7.
    try:
        status = client.client.check_authentication()
        print("Authentication OK:", status)
    except Exception as exc:  # noqa: BLE001 - smoke test surfaces any failure
        print("Authentication check failed:", type(exc).__name__, exc)
        raise


if __name__ == "__main__":
    main()
