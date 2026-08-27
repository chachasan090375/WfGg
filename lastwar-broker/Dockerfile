FROM golang:1.25-bookworm AS build

ARG LASTWAR_CLIENT_REVISION=ee5f64de160a8051c2f9f98189b75038dd225a0a

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --filter=blob:none https://github.com/ljagiello/lastwar-client.git . \
 && git checkout "${LASTWAR_CLIENT_REVISION}"

COPY patches/0001-wfgg-staged-email-auth.patch /tmp/0001-wfgg-staged-email-auth.patch
RUN git apply --check /tmp/0001-wfgg-staged-email-auth.patch \
 && git apply /tmp/0001-wfgg-staged-email-auth.patch

COPY go/wfgg-broker-main.go /src/cmd/wfgg-broker/main.go

RUN go test ./internal/auth ./internal/session ./internal/sfs \
 && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/wfgg-lastwar-broker ./cmd/wfgg-broker

FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV HOME=/tmp
ENV PORT=8080
WORKDIR /app
COPY --from=build /out/wfgg-lastwar-broker /app/wfgg-lastwar-broker
USER nobody
EXPOSE 8080
ENTRYPOINT ["/app/wfgg-lastwar-broker"]
