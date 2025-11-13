
package atp.policy

default allow = true

forbidden_tools := {"fs.write"}

deny[msg] {
  some t
  input.meta.tool_permissions[t]
  forbidden_tools[input.meta.tool_permissions[t]]
  msg := {"code":"EPOLICY","reason":"forbidden tool"}
}
