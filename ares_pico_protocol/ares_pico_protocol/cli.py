"""Hardware bring-up CLI. This intentionally has no ROS topic dependency."""

from __future__ import annotations

import argparse
import json

from .client import AresPicoClient


def _byte(value: str) -> int:
    parsed = int(value, 0)
    if not 0 <= parsed <= 255:
        raise argparse.ArgumentTypeError('color channel must be in 0..255')
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description='Test an ares_led_driver device')
    parser.add_argument('--port', default='auto')
    parser.add_argument('--timeout', type=float, default=0.5)
    subparsers = parser.add_subparsers(dest='command', required=True)
    subparsers.add_parser('ping')
    subparsers.add_parser('status')

    solid = subparsers.add_parser('solid')
    solid.add_argument('count', type=int)
    solid.add_argument('red', type=_byte)
    solid.add_argument('green', type=_byte)
    solid.add_argument('blue', type=_byte)

    args = parser.parse_args()
    with AresPicoClient(args.port, timeout=args.timeout) as client:
        if args.command == 'ping':
            print(client.ping())
        elif args.command == 'status':
            print(json.dumps(client.get_status().__dict__, indent=2))
        elif args.command == 'solid':
            pixel = bytes((args.red, args.green, args.blue))
            ack = client.configure_and_send(pixel * args.count)
            print(ack)


if __name__ == '__main__':
    main()
