import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import PageHeader from "../components/PageHeader";
import { ChartIcon } from "../components/icons";

interface EmbedUrlResponse {
  embed_url: string;
}

export default function AnalyticsPage() {
  const [embedUrl, setEmbedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notReady, setNotReady] = useState(false);

  useEffect(() => {
    api
      .get<EmbedUrlResponse>("/v1/analytics/embed-url")
      .then((res) => setEmbedUrl(res.embed_url))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotReady(true);
        } else {
          setError(err instanceof ApiError ? err.detail : String(err));
        }
      });
  }, []);

  return (
    <div className="analytics-page">
      <PageHeader
        icon={<ChartIcon />}
        title="Analytics"
        subtitle="Fleet-wide risk, alert and telemetry trends."
      />
      {notReady && (
        <p className="problem-banner">
          Analytics isn't available right now. Please try again in a moment.
        </p>
      )}
      {error && <p className="problem-banner">{error}</p>}
      {embedUrl && (
        <iframe
          src={embedUrl}
          title="Fleet Overview"
          className="analytics-frame"
          frameBorder={0}
        />
      )}
    </div>
  );
}
