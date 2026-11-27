import next from "eslint-config-next/core-web-vitals";

// Retain the existing React hooks rules; the optional React Compiler is not enabled.
export default [
  ...next,
  { rules: { "react-hooks/set-state-in-effect": "off", "react-hooks/refs": "off" } },
];
