package main
import (
  "encoding/json"
  "fmt"
  "time"
)

type Frame struct {
  Type string `json:"type"`
  Ts int64 `json:"ts"`
  Payload map[string]interface{} `json:"payload"`
}

func BuildFrame(t string, payload map[string]interface{}) Frame {
  return Frame{Type: t, Ts: time.Now().UnixMilli(), Payload: payload}
}
func Serialize(f Frame) ([]byte, error) { return json.Marshal(f) }
func Deserialize(b []byte) (Frame, error) { var f Frame; err := json.Unmarshal(b, &f); return f, err }

func roundTrip() error {
  f := BuildFrame("ping", map[string]interface{}{"n":1})
  b, err := Serialize(f); if err != nil { return err }
  d, err := Deserialize(b); if err != nil { return err }
  if d.Type != "ping" || int(d.Payload["n"].(float64)) != 1 { return fmt.Errorf("round trip failed") }
  fmt.Println("OK: go sdk POC passed")
  return nil
}

func main(){
  if err := roundTrip(); err != nil { panic(err) }
}
