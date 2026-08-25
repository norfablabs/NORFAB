import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, Button, Center, Stack } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export default class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("NFWeb frontend failed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Center component="main" className="fatal-error">
        <Stack maw={640}>
          <Alert
            color="red"
            title="NFWeb could not render this view"
            icon={<IconAlertTriangle size={18} />}
          >
            {this.state.error.message}
          </Alert>
          <Button onClick={() => window.location.reload()}>Reload NFWeb</Button>
        </Stack>
      </Center>
    );
  }
}
