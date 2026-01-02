import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { instanceAPI, Instance, getErrorMessage } from '../utils/api';
import Navigation from '../components/Navigation';
import RestoreModal from '../components/RestoreModal';
import { useAbortController, isAbortError } from '../hooks/useAbortController';
import { useUser } from '../contexts/UserContext';

const Instances: React.FC = () => {
  const { profile, loading: profileLoading } = useUser();
  const [instances, setInstances] = useState<Instance[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [restoreModalOpen, setRestoreModalOpen] = useState(false);
  const [restoreInstance, setRestoreInstance] = useState<Instance | null>(null);
  const location = useLocation();
  const { getSignal, isAborted } = useAbortController();
  const lastFetchRef = useRef<number>(0);
  const STALE_TIME = 30000; // 30 seconds debounce for visibility/focus refetch

  const fetchInstances = useCallback(async (signal?: AbortSignal) => {
    if (!profile?.id) return;

    try {
      setLoading(true);

      const instancesResponse = await instanceAPI.list(profile.id, signal);
      if (isAborted()) return;
      setInstances(instancesResponse.data.instances || []);
      lastFetchRef.current = Date.now();

    } catch (err: unknown) {
      if (isAbortError(err)) return;
      if (!isAborted()) {
        setError(getErrorMessage(err, 'Failed to load instances'));
      }
    } finally {
      if (!isAborted()) {
        setLoading(false);
      }
    }
  }, [profile?.id, isAborted]);

  // Fetch instances when profile is available
  useEffect(() => {
    if (profile?.id) {
      fetchInstances(getSignal());
    }
  }, [location.key, profile?.id, fetchInstances, getSignal]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden && Date.now() - lastFetchRef.current > STALE_TIME) {
        fetchInstances(getSignal());
      }
    };

    const handleFocus = () => {
      if (Date.now() - lastFetchRef.current > STALE_TIME) {
        fetchInstances(getSignal());
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleFocus);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
    };
  }, [fetchInstances, getSignal]);

  const handleInstanceAction = useCallback(async (instanceId: string, action: string, parameters?: Record<string, unknown>) => {
    if (!profile?.id) return;

    try {
      setActionLoading(instanceId);
      setError('');

      await instanceAPI.action(instanceId, action, parameters);

      // Poll for status change with exponential backoff
      const pollForStatusChange = async (maxAttempts = 10): Promise<void> => {
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
          await new Promise(resolve =>
            setTimeout(resolve, Math.min(1000 * Math.pow(1.5, attempt), 5000))
          );

          // Fetch fresh instances data and check status
          const instancesResponse = await instanceAPI.list(profile.id);
          setInstances(instancesResponse.data.instances || []);

          // Check if the instance status has changed (action completed)
          const instance = instancesResponse.data.instances?.find((i: Instance) => i.id === instanceId);
          if (instance && !['creating', 'starting', 'stopping'].includes(instance.status)) {
            return;
          }
        }
      };

      await pollForStatusChange();

    } catch (err: unknown) {
      setError(getErrorMessage(err, `Failed to ${action} instance`));
    } finally {
      setActionLoading(null);
    }
  }, [profile?.id]);

  const handleRestoreInstance = useCallback(async (instanceId: string, backupId: string) => {
    await handleInstanceAction(instanceId, 'restore', { backup_id: backupId });
  }, [handleInstanceAction]);

  const openRestoreModal = useCallback((instance: Instance) => {
    setRestoreInstance(instance);
    setRestoreModalOpen(true);
  }, []);

  const closeRestoreModal = useCallback(() => {
    setRestoreModalOpen(false);
    setRestoreInstance(null);
  }, []);

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { class: string; icon: JSX.Element; label: string }> = {
      running: {
        class: 'badge-success',
        icon: <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full mr-1.5 animate-pulse"></span>,
        label: 'Running'
      },
      stopped: {
        class: 'badge-neutral',
        icon: <span className="w-1.5 h-1.5 bg-warm-400 rounded-full mr-1.5"></span>,
        label: 'Stopped'
      },
      creating: {
        class: 'badge-info',
        icon: <svg className="w-3 h-3 mr-1.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>,
        label: 'Creating'
      },
      starting: {
        class: 'badge-info',
        icon: <svg className="w-3 h-3 mr-1.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>,
        label: 'Starting'
      },
      stopping: {
        class: 'badge-warning',
        icon: <svg className="w-3 h-3 mr-1.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>,
        label: 'Stopping'
      },
      error: {
        class: 'badge-error',
        icon: <span className="w-1.5 h-1.5 bg-rose-500 rounded-full mr-1.5"></span>,
        label: 'Error'
      },
      terminated: {
        class: 'badge-error',
        icon: <span className="w-1.5 h-1.5 bg-rose-500 rounded-full mr-1.5"></span>,
        label: 'Terminated'
      },
      paused: {
        class: 'badge-warning',
        icon: <span className="w-1.5 h-1.5 bg-amber-500 rounded-full mr-1.5"></span>,
        label: 'Paused'
      }
    };
    return badges[status] || { class: 'badge-neutral', icon: <span className="w-1.5 h-1.5 bg-warm-400 rounded-full mr-1.5"></span>, label: status };
  };

  const getBillingBadge = (status: string) => {
    const badges: Record<string, { class: string; label: string }> = {
      paid: { class: 'badge-success', label: 'Paid' },
      trial: { class: 'badge-warning', label: 'Trial' },
      payment_required: { class: 'badge-error', label: 'Payment Due' }
    };
    return badges[status] || { class: 'badge-neutral', label: 'Unknown' };
  };

  const getActionButtons = (instance: Instance) => {
    const buttons = [];
    const isLoading = actionLoading === instance.id;

    const buttonBase = "inline-flex items-center justify-center px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-200 disabled:opacity-50";

    if (instance.status === 'paused') {
      buttons.push(
        <button
          key="unpause"
          onClick={() => handleInstanceAction(instance.id, 'unpause')}
          disabled={isLoading}
          className={`${buttonBase} bg-emerald-500 text-white hover:bg-emerald-600 shadow-sm`}
        >
          {isLoading ? (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          ) : (
            <>
              <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              </svg>
              Unpause
            </>
          )}
        </button>
      );
      return buttons;
    }

    if (['stopped', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="start"
          onClick={() => handleInstanceAction(instance.id, 'start')}
          disabled={isLoading}
          className={`${buttonBase} bg-emerald-500 text-white hover:bg-emerald-600 shadow-sm`}
        >
          {isLoading ? (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          ) : (
            <>
              <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              </svg>
              Start
            </>
          )}
        </button>
      );
    }

    if (['running', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="stop"
          onClick={() => handleInstanceAction(instance.id, 'stop')}
          disabled={isLoading}
          className={`${buttonBase} bg-rose-500 text-white hover:bg-rose-600 shadow-sm`}
        >
          {isLoading ? (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          ) : (
            <>
              <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
              </svg>
              Stop
            </>
          )}
        </button>
      );
    }

    if (['running'].includes(instance.status)) {
      buttons.push(
        <button
          key="backup"
          onClick={() => handleInstanceAction(instance.id, 'backup')}
          disabled={isLoading}
          className={`${buttonBase} bg-primary-500 text-white hover:bg-primary-600 shadow-sm`}
        >
          {isLoading ? (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          ) : (
            <>
              <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              Backup
            </>
          )}
        </button>
      );
    }

    if (['running', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="restart"
          onClick={() => handleInstanceAction(instance.id, 'restart')}
          disabled={isLoading}
          className={`${buttonBase} bg-amber-500 text-white hover:bg-amber-600 shadow-sm`}
        >
          {isLoading ? (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          ) : (
            <>
              <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Restart
            </>
          )}
        </button>
      );
    }

    if (['stopped', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="restore"
          onClick={() => openRestoreModal(instance)}
          disabled={isLoading}
          className={`${buttonBase} bg-violet-500 text-white hover:bg-violet-600 shadow-sm`}
        >
          {isLoading ? (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
          ) : (
            <>
              <svg className="w-3.5 h-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
              Restore
            </>
          )}
        </button>
      );
    }

    return buttons;
  };

  const totalInstances = instances.length;
  const runningInstances = instances.filter(i => i.status === 'running').length;

  // Show loading while profile or instances are loading
  const isLoading = profileLoading || (profile && loading);

  if (isLoading) {
    return (
      <>
        <Navigation userProfile={profile ?? undefined} />
        <div className="min-h-screen flex items-center justify-center bg-warm-50">
          <div className="flex flex-col items-center animate-fade-in">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-primary-200 rounded-full"></div>
              <div className="w-16 h-16 border-4 border-primary-600 rounded-full animate-spin absolute top-0 left-0 border-t-transparent"></div>
            </div>
            <p className="mt-4 text-warm-600 font-medium">Loading instances...</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile ?? undefined} />

      <main className="min-h-screen bg-warm-50 bg-mesh">
        <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-8 animate-fade-in">
            <div className="mb-4 sm:mb-0">
              <h1 className="text-3xl font-bold text-warm-900">My Instances</h1>
              <p className="mt-2 text-warm-500 flex items-center">
                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-warm-100 text-warm-600 mr-2">
                  {totalInstances} total
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-50 text-emerald-600">
                  <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full mr-1.5 animate-pulse"></span>
                  {runningInstances} running
                </span>
              </p>
            </div>
            <Link
              to="/instances/create"
              className="btn-primary"
            >
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create Instance
            </Link>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-6 animate-fade-in-down bg-rose-50 border border-rose-200 text-rose-700 px-5 py-4 rounded-xl flex items-start">
              <svg className="w-5 h-5 mr-3 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{error}</span>
              <button onClick={() => setError('')} className="ml-auto text-rose-500 hover:text-rose-700">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}

          {/* Instances */}
          {instances.length === 0 ? (
            <div className="card p-12 text-center animate-fade-in-up">
              <div className="w-20 h-20 bg-gradient-to-br from-primary-100 to-primary-200 rounded-2xl flex items-center justify-center mx-auto mb-6">
                <svg className="w-10 h-10 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-warm-900 mb-2">No instances found</h3>
              <p className="text-warm-500 mb-8 max-w-md mx-auto">
                Deploy your first Odoo instance in minutes. Choose from multiple versions and configurations.
              </p>
              <Link to="/instances/create" className="btn-primary">
                <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Create Instance
              </Link>
            </div>
          ) : (
            <div className="space-y-4 animate-fade-in-up">
              {instances.map((instance, index) => {
                const statusBadge = getStatusBadge(instance.status);
                const billingBadge = getBillingBadge(instance.billing_status);

                return (
                  <div
                    key={instance.id}
                    className="card p-4 sm:p-6 card-hover"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <div className="flex flex-col gap-4">
                      {/* Instance info */}
                      <div className="flex items-start space-x-3 sm:space-x-4">
                        <div className="w-12 h-12 sm:w-14 sm:h-14 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl flex items-center justify-center flex-shrink-0">
                          <span className="text-primary-700 font-bold text-lg sm:text-xl">
                            {instance.name[0].toUpperCase()}
                          </span>
                        </div>
                        <div className="min-w-0 flex-1">
                          {/* Name and badges - stack on mobile */}
                          <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 mb-1">
                            <h3 className="text-base sm:text-lg font-semibold text-warm-900 truncate">
                              {instance.name}
                            </h3>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className={`badge text-xs ${statusBadge.class} flex items-center`}>
                                {statusBadge.icon}
                                {statusBadge.label}
                              </span>
                              <span className={`badge text-xs ${billingBadge.class}`}>
                                {billingBadge.label}
                              </span>
                            </div>
                          </div>
                          <p className="text-xs sm:text-sm text-warm-500 mb-2 line-clamp-1">
                            {instance.description || 'No description'}
                          </p>
                          {/* Meta info - hide some on mobile */}
                          <div className="flex flex-wrap items-center gap-x-3 sm:gap-x-4 gap-y-1 text-xs text-warm-500">
                            <span className="inline-flex items-center">
                              <svg className="w-3 h-3 sm:w-3.5 sm:h-3.5 mr-1 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                              </svg>
                              {instance.instance_type}
                            </span>
                            <span className="inline-flex items-center">
                              <svg className="w-3 h-3 sm:w-3.5 sm:h-3.5 mr-1 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                              </svg>
                              Odoo {instance.odoo_version}
                            </span>
                            <span className="hidden sm:inline-flex items-center">
                              <svg className="w-3.5 h-3.5 mr-1 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                              </svg>
                              {instance.database_name}
                            </span>
                            <span className="inline-flex items-center">
                              <svg className="w-3 h-3 sm:w-3.5 sm:h-3.5 mr-1 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                              </svg>
                              {new Date(instance.created_at).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Actions - separate row on mobile, inline on larger screens */}
                      <div className="flex items-center justify-end gap-2 flex-wrap border-t border-warm-100 pt-3 -mx-4 px-4 sm:mx-0 sm:px-0 sm:border-0 sm:pt-0">
                        {instance.external_url && (
                          <a
                            href={instance.external_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn-secondary py-1.5 px-3 text-xs"
                          >
                            <svg className="w-3.5 h-3.5 sm:mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                            <span className="hidden sm:inline">Open</span>
                          </a>
                        )}
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {getActionButtons(instance)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Mobile FAB */}
        <Link
          to="/instances/create"
          className="sm:hidden fixed bottom-6 right-6 w-14 h-14 bg-gradient-to-br from-primary-600 to-primary-500 rounded-full shadow-soft-lg flex items-center justify-center text-white hover:shadow-glow transition-all duration-300 hover:scale-105 z-50"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </Link>
      </main>

      {/* Restore Modal */}
      {restoreInstance && (
        <RestoreModal
          instance={restoreInstance}
          isOpen={restoreModalOpen}
          onClose={closeRestoreModal}
          onRestore={handleRestoreInstance}
        />
      )}
    </>
  );
};

export default Instances;
