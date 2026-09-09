# Security Policy

## Supported Versions

Security updates are provided for the latest version of this project.

## Reporting a Vulnerability

If you discover a security vulnerability in API Monitor, please report it privately rather than opening a public GitHub issue.

When reporting a vulnerability, please include:

- A clear description of the issue
- Steps to reproduce the vulnerability
- The potential security impact
- Any relevant logs, screenshots, or proof of concept
- Suggested mitigation, if available

Please do not include passwords, API keys, access tokens, or other sensitive credentials in the report.

## Security Practices

This project follows several security practices:

- Environment variables are used for sensitive configuration.
- Secrets and local environment files are excluded from Git.
- API authentication uses JWT and API key mechanisms where appropriate.
- API keys are stored using secure hashing.
- Production configuration supports HTTPS and secure cookies.
- Django security checks are used to identify deployment-related security issues.
- Dependency vulnerabilities are monitored through GitHub Dependabot.
- Code security issues are monitored through GitHub Code Scanning.

## Responsible Disclosure

Please allow reasonable time for a vulnerability to be investigated and addressed before publicly disclosing it.