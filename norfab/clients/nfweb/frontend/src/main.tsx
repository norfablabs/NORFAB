import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createTheme, MantineProvider } from "@mantine/core";
import "@mantine/core/styles.css";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./styles.css";

const theme = createTheme({
  primaryColor: "fabric",
  primaryShade: { light: 6, dark: 4 },
  defaultRadius: "sm",
  fontFamily:
    '"Segoe UI Variable Text", "Segoe UI", ui-sans-serif, system-ui, sans-serif',
  headings: {
    fontFamily:
      '"Segoe UI Variable Display", "Segoe UI", ui-sans-serif, system-ui, sans-serif',
  },
  colors: {
    fabric: [
      "#e7f8f5",
      "#cceee8",
      "#9edfd5",
      "#70cec0",
      "#4bbbad",
      "#36a598",
      "#2c887e",
      "#286d66",
      "#255853",
      "#214a46",
    ],
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider forceColorScheme="dark" theme={theme}>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </MantineProvider>
  </StrictMode>,
);
