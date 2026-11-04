"""Portable headless service entry point: python -m app."""
import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description='Start the FRED local assistant service.')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    uvicorn.run('app.main:app', host='127.0.0.1', port=args.port, access_log=False,
                timeout_graceful_shutdown=20)


if __name__ == '__main__':
    main()
