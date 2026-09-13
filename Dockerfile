FROM alpine:3.23 AS microsocks-build

WORKDIR /build
RUN apk add --no-cache build-base ca-certificates curl xz \
    && curl -fL --retry 3 \
       https://ftp.barfooze.de/pub/sabotage/tarballs/microsocks-1.0.5.tar.xz \
       -o microsocks.tar.xz \
    && printf '%s  microsocks.tar.xz\n' \
       '16b99f1b94dd857f6ee303f2fb3ef85acd5d8cad2a7635bca7d78c3106bd9beb846a4363286d2d1f395a9bcc115890736c883835590f22234e7955fab6066a66' \
       | sha512sum -c - \
    && tar -xJf microsocks.tar.xz \
    && make -C microsocks-1.0.5

FROM alpine:3.23

RUN apk add --no-cache bash ca-certificates iptables openvpn su-exec \
    && adduser -D -H socks

COPY --from=microsocks-build /build/microsocks-1.0.5/microsocks /usr/local/bin/microsocks
COPY --from=microsocks-build /build/microsocks-1.0.5/COPYING /usr/share/licenses/microsocks/COPYING
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 1080
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
