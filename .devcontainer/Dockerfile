FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# PAS uses npm. Older base images retain a Yarn apt source with an expired key.
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn.sources
