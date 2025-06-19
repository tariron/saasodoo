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
        // Use fallback config
        setConfig({
          BASE_DOMAIN: 'saasodoo.local',
          ENVIRONMENT: 'development',
          API_BASE_URL: 'https://api.saasodoo.local',
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