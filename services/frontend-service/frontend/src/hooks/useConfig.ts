import { useState, useEffect } from 'react';
import { configAPI, AppConfig } from '../utils/api';

export const useConfig = () => {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await configAPI.getConfig();
        setConfig(response.data);
      } catch (err: any) {
        setError('Failed to load configuration');
        // Use fallback config based on window.location
        const hostname = window.location.hostname;
        const protocol = window.location.protocol;

        let apiBaseUrl: string;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          // When accessing via localhost, use port-based access
          apiBaseUrl = `${protocol}//localhost:8003`;
        } else {
          // Extract domain from hostname (e.g., app.example.com -> api.example.com)
          const domain = hostname.replace(/^app\./, '');
          apiBaseUrl = `${protocol}//api.${domain}`;
        }

        setConfig({
          BASE_DOMAIN: hostname.replace(/^app\./, ''),
          ENVIRONMENT: 'development',
          API_BASE_URL: apiBaseUrl,
          VERSION: '1.0.0',
          FEATURES: {
            billing: true,
            analytics: false,
            monitoring: true
          }
        });
      } finally {
        setLoading(false);
      }
    };

    fetchConfig();
  }, []);

  return { config, loading, error };
};