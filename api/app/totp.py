import argparse
import os

from .security import totp_code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secret", default=os.environ.get("ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXP"))
    args = ap.parse_args()
    print(totp_code(args.secret.upper()))


if __name__ == "__main__":
    main()
