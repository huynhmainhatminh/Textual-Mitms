import argparse
from .app import TextualMitms


def main():
    parser = argparse.ArgumentParser(
        description="Textual-Mitms — Terminal MITM proxy UI"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Proxy listen host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Proxy listen port (default: 8080)",
    )
    args = parser.parse_args()
    app = TextualMitms(listen_host=args.host, listen_port=args.port)
    app.run()


if __name__ == "__main__":
    main()