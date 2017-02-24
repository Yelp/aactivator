FROM debian:stretch

# The default mirrors are too flaky to run reliably in CI.
RUN sed -E \
    '/security\.debian/! s@http://[^/]+/@http://mirrors.kernel.org/@' \
    -i /etc/apt/sources.list

RUN apt-get update  \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        devscripts \
        dumb-init \
        equivs \
        lintian \
    && apt-get clean

WORKDIR /mnt
CMD [ \
    "dumb-init", \
    "sh", "-euxc", \
    "mk-build-deps -ir --tool 'apt-get --no-install-recommends -y' debian/control && make builddeb" \
]
