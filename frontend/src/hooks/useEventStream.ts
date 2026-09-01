import { useEffect, useRef } from 'react';

export interface EventStreamEvent {
  type: string;
  [key: string]: unknown;
}

export function useEventStream(
  onEvent: (event: EventStreamEvent) => void,
) {
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      if (stopped) return;

      const source = new EventSource('/api/events/stream');
      eventSource = source;
      source.onmessage = event => {
        try {
          onEventRef.current(JSON.parse(event.data) as EventStreamEvent);
        } catch {
          // Ignore malformed events; polling remains the source-of-truth fallback.
        }
      };
      source.onerror = () => {
        source.close();
        if (eventSource === source) eventSource = null;
        if (!stopped && reconnectTimer === null) {
          reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connect();
          }, 5_000);
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      eventSource?.close();
    };
  }, []);
}
