"""Forward a remote loopback port to this computer's Moyu Whistle service."""
import argparse
import subprocess


def command(host, local_port, remote_port, ssh_port=22):
    if not host or host.startswith("-") or any(c.isspace() for c in host):
        raise ValueError("Use an SSH config alias or user@host")
    if not all(1 <= p <= 65535 for p in (local_port, remote_port, ssh_port)):
        raise ValueError("Invalid port")
    return ["ssh", "-p", str(ssh_port), "-N", "-T", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3", "-R",
            f"127.0.0.1:{remote_port}:127.0.0.1:{local_port}", host]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("--local-port", type=int, default=17321)
    parser.add_argument("--remote-port", type=int, default=17322)
    parser.add_argument("--ssh-port", type=int, default=22)
    args = parser.parse_args()
    try:
        raise SystemExit(subprocess.call(command(args.host, args.local_port, args.remote_port, args.ssh_port)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
