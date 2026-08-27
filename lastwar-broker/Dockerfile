FROM golang:1.27-bookworm AS build

ARG LASTWAR_CLIENT_REVISION=ee5f64de160a8051c2f9f98189b75038dd225a0a

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --filter=blob:none https://github.com/ljagiello/lastwar-client.git . \
 && git checkout "${LASTWAR_CLIENT_REVISION}"

COPY patches/apply-staged-email-auth.py /tmp/apply-staged-email-auth.py
RUN python3 /tmp/apply-staged-email-auth.py /src/internal/auth/login.go \
 && git diff --check \
 && grep -q "VerificationCodeProvider func() (string, error)" /src/internal/auth/login.go \
 && grep -q "OnVerificationCodeSent" /src/internal/auth/login.go

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
