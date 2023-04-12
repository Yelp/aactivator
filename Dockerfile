FROM ubuntu:jammy

RUN apt-get update  \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential=12.9ubuntu3 \ 
        devscripts=2.22.* \ 
        dumb-init=1.2.* \ 
        equivs=2.3.* \ 
        lintian=2.114.* \ 
    && apt-get clean

WORKDIR /mnt
CMD [ \
    "dumb-init", \
    "sh", "-euxc", \
    "mk-build-deps -ir --tool 'apt-get --no-install-recommends -y' debian/control && make builddeb" \
]
