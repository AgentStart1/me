package main

import (
    "fmt"
    "net"
    "net/http"
    "os"
)

func main() {
    listeners := make([]net.Listener, 0, 70)
    for port := 21000; port < 21070; port++ {
        listener, err := net.Listen("tcp", fmt.Sprintf("0.0.0.0:%d", port))
        if err != nil { panic(err) }
        listeners = append(listeners, listener)
    }
    handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprint(w, "gvproxy-application-ok")
    })
    for _, listener := range listeners {
        go http.Serve(listener, handler)
    }
    if err := os.WriteFile("/tmp/me-gvproxy-http/ready", []byte("ready"), 0600); err != nil { panic(err) }
    select {}
}
