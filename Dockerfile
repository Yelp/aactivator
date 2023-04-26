FROM ubuntu:jammy

RUN apt-get update  \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        devscripts \
        dumb-init \
        equivs \
        lintian \
    && apt-get clean

# debuild will fail when running directly against /mnt, so we copy the files we need
RUN mkdir /build
COPY debian /build/debian
COPY Makefile aactivator.py /build/
WORKDIR /build

CMD [ \
    "dumb-init", \
    "sh", "-euxc", \
    "mk-build-deps -ir --tool 'apt-get --no-install-recommends -y' debian/control && make builddeb && cp ./dist/* /mnt/dist" \
]
