// Small inline SVGs (feather-style, stroke currentColor) instead of an icon
// library dependency — the app has no icon usage today, and a handful of
// nav/stat icons doesn't justify a new package for a hackathon POC.
import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function base(props: IconProps, children: ReactNode) {
  const { width = 18, height = 18, ...rest } = props;
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      {children}
    </svg>
  );
}

export function TruckIcon(props: IconProps) {
  return base(
    props,
    <>
      <path d="M1 3h13v13H1z" />
      <path d="M14 8h4l3 3v5h-7V8z" />
      <circle cx="5.5" cy="18.5" r="1.8" />
      <circle cx="17.5" cy="18.5" r="1.8" />
    </>,
  );
}

export function AlertIcon(props: IconProps) {
  return base(
    props,
    <>
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </>,
  );
}

export function ChatIcon(props: IconProps) {
  return base(
    props,
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />,
  );
}

export function ChartIcon(props: IconProps) {
  return base(
    props,
    <>
      <line x1="12" y1="20" x2="12" y2="10" />
      <line x1="18" y1="20" x2="18" y2="4" />
      <line x1="6" y1="20" x2="6" y2="16" />
    </>,
  );
}

export function ListIcon(props: IconProps) {
  return base(
    props,
    <>
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </>,
  );
}

export function GaugeIcon(props: IconProps) {
  return base(
    props,
    <>
      <path d="M12 15 15.5 8.5" />
      <path d="M3 12a9 9 0 1 1 18 0" />
      <path d="M3 12h1M20 12h1M12 3v1" />
    </>,
  );
}

export function ClockIcon(props: IconProps) {
  return base(
    props,
    <>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </>,
  );
}

export function WrenchIcon(props: IconProps) {
  return base(
    props,
    <path d="M14.7 6.3a4 4 0 1 1-5.4 5.4l-6.6 6.6a1.5 1.5 0 0 0 2.1 2.1l6.6-6.6a4 4 0 0 1 5.4-5.4L13 6l1 1 2.8-2.8a5.8 5.8 0 0 0-2.1-.9 6 6 0 1 0 0 5.4z" />,
  );
}

export function InboxIcon(props: IconProps) {
  return base(
    props,
    <>
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </>,
  );
}

export function MapPinIcon(props: IconProps) {
  return base(
    props,
    <>
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </>,
  );
}
