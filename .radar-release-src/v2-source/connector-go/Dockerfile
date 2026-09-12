FROM golang:1.27-bookworm AS native-build
ARG LASTWAR_CLIENT_REVISION=ee5f64de160a8051c2f9f98189b75038dd225a0a
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /lastwar
RUN git clone --filter=blob:none https://github.com/ljagiello/lastwar-client.git . \
 && git checkout "${LASTWAR_CLIENT_REVISION}"
COPY native-template/main.go /lastwar/cmd/wfgg-radar-native-template/main.go
RUN gofmt -w /lastwar/cmd/wfgg-radar-native-template/main.go \
 && go test ./internal/auth ./internal/pcap ./internal/sfs \
 && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -tags lastwar_native_template -trimpath -ldflags="-s -w" -o /out/radar-native-template ./cmd/wfgg-radar-native-template

FROM golang:1.23-alpine AS connector-build
WORKDIR /src
COPY go.mod ./
COPY . .
RUN go test ./... \
 && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/radar-connector ./cmd/radar-connector

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=connector-build /out/radar-connector /radar-connector
COPY --from=native-build /out/radar-native-template /radar-native-template
USER nonroot:nonroot
EXPOSE 8788
ENTRYPOINT ["/radar-connector"]
