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
COPY patches/apply-broker-child-runtime.py /tmp/apply-broker-child-runtime.py
COPY patches/apply-recursive-uid-match.py /tmp/apply-recursive-uid-match.py
COPY patches/apply-reconnect-session-v2.py /tmp/apply-reconnect-session-v2.py
COPY patches/apply-v1-relink-guard.py /tmp/apply-v1-relink-guard.py
RUN python3 /tmp/apply-broker-child-runtime.py /src/cmd/wfgg-broker/main.go \
 && python3 /tmp/apply-recursive-uid-match.py /src/cmd/wfgg-broker/main.go \
 && python3 /tmp/apply-reconnect-session-v2.py /src/cmd/wfgg-broker/main.go \
 && python3 /tmp/apply-v1-relink-guard.py /src/cmd/wfgg-broker/main.go \
 && grep -q '127.0.0.1:' /src/cmd/wfgg-broker/main.go \
 && grep -q 'nestedValueContainsUID' /src/cmd/wfgg-broker/main.go \
 && grep -q 'role-session-v2' /src/cmd/wfgg-broker/main.go \
 && grep -q 'DoCrossServerLogin' /src/cmd/wfgg-broker/main.go \
 && grep -q 'LASTWAR_RELINK_REQUIRED' /src/cmd/wfgg-broker/main.go \
 && git diff --check

RUN go test ./internal/auth ./internal/session ./internal/sfs \
 && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/wfgg-lastwar-child ./cmd/wfgg-broker

FROM python:3.13-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV PORT=8080
ENV WFGG_BROKER_SLOTS=4
ENV WFGG_BROKER_CHILD_BIN=/app/wfgg-lastwar-child
WORKDIR /app
COPY --from=build /out/wfgg-lastwar-child /app/wfgg-lastwar-child
COPY manager/wfgg_broker_manager.py /app/wfgg_broker_manager.py
RUN chmod 0755 /app/wfgg-lastwar-child /app/wfgg_broker_manager.py

USER nobody
EXPOSE 8080
ENTRYPOINT ["python3", "/app/wfgg_broker_manager.py"]
