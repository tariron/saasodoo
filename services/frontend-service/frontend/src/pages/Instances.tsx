import React, { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { instanceAPI, authAPI, Instance, UserProfile } from '../utils/api';
import Navigation from '../components/Navigation';
import RestoreModal from '../components/RestoreModal';

const Instances: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [searchParams] = useSearchParams();
  const [restoreModalOpen, setRestoreModalOpen] = useState(false);
  const [restoreInstance, setRestoreInstance] = useState<Instance | null>(null);

  const fetchInitialData = async () => {
    try {
      setLoading(true);
      
      // Fetch user profile
      const profileResponse = await authAPI.getProfile();
      setProfile(profileResponse.data);

      // Fetch instances for this customer
      const instancesResponse = await instanceAPI.list(profileResponse.data.id);
      setInstances(instancesResponse.data.instances || []);
      
    } catch (err: any) {
      setError('Failed to load instances data');
      console.error('Instances page error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  const handleInstanceAction = async (instanceId: string, action: string, parameters?: any) => {
    try {
      setActionLoading(instanceId);
      setError('');
      
      console.log(`🔵 Starting ${action} action for instance:`, instanceId);
      await instanceAPI.action(instanceId, action, parameters);
      console.log(`✅ ${action} action queued successfully`);
      
      // Wait for backend to process the action (since actions are asynchronous)
      console.log('⏳ Waiting 3 seconds for backend processing...');
      await new Promise(resolve => setTimeout(resolve, 3000));
      
      // Refresh instances after delay to get updated status
      console.log('🔄 Refreshing instance data...');
      await fetchInitialData();
      console.log('✅ Instance data refreshed');
      
    } catch (err: any) {
      console.error(`❌ ${action} action failed:`, err);
      const errorMessage = err.response?.data?.detail || `Failed to ${action} instance`;
      setError(errorMessage);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRestoreInstance = async (instanceId: string, backupId: string) => {
    await handleInstanceAction(instanceId, 'restore', { backup_id: backupId });
  };

  const openRestoreModal = (instance: Instance) => {
    setRestoreInstance(instance);
    setRestoreModalOpen(true);
  };

  const closeRestoreModal = () => {
    setRestoreModalOpen(false);
    setRestoreInstance(null);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'text-green-700 bg-green-100';
      case 'stopped': return 'text-gray-700 bg-gray-100';
      case 'creating': return 'text-blue-700 bg-blue-100';
      case 'starting': return 'text-blue-700 bg-blue-100';
      case 'stopping': return 'text-yellow-700 bg-yellow-100';
      case 'error': return 'text-red-700 bg-red-100';
      case 'terminated': return 'text-red-700 bg-red-100';
      default: return 'text-gray-700 bg-gray-100';
    }
  };

  const getActionButtons = (instance: Instance) => {
    const buttons = [];
    const isLoading = actionLoading === instance.id;

    // Start button: available for stopped or error instances
    if (['stopped', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="start"
          onClick={() => handleInstanceAction(instance.id, 'start')}
          disabled={isLoading}
          className="text-xs bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50"
        >
          {isLoading ? '...' : 'Start'}
        </button>
      );
    }

    // Stop button: available for running, paused, or error instances
    if (['running', 'paused', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="stop"
          onClick={() => handleInstanceAction(instance.id, 'stop')}
          disabled={isLoading}
          className="text-xs bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 disabled:opacity-50"
        >
          {isLoading ? '...' : 'Stop'}
        </button>
      );
    }

    // Backup button: available for running or paused instances (not error to avoid corrupted backups)
    if (['running', 'paused'].includes(instance.status)) {
      buttons.push(
        <button
          key="backup"
          onClick={() => handleInstanceAction(instance.id, 'backup')}
          disabled={isLoading}
          className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {isLoading ? '...' : 'Backup'}
        </button>
      );
    }

    // Restart button: available for running, paused, or error instances
    if (['running', 'paused', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="restart"
          onClick={() => handleInstanceAction(instance.id, 'restart')}
          disabled={isLoading}
          className="text-xs bg-yellow-600 text-white px-3 py-1 rounded hover:bg-yellow-700 disabled:opacity-50"
        >
          {isLoading ? '...' : 'Restart'}
        </button>
      );
    }

    // Restore button: available for stopped or error instances
    if (['stopped', 'error'].includes(instance.status)) {
      buttons.push(
        <button
          key="restore"
          onClick={() => openRestoreModal(instance)}
          disabled={isLoading}
          className="text-xs bg-purple-600 text-white px-3 py-1 rounded hover:bg-purple-700 disabled:opacity-50"
        >
          {isLoading ? '...' : 'Restore'}
        </button>
      );
    }

    return buttons;
  };

  const totalInstances = instances.length;
  const runningInstances = instances.filter(i => i.status === 'running').length;

  if (loading) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="flex flex-col items-center">
            <svg className="animate-spin h-8 w-8 text-primary-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p className="mt-2 text-sm text-gray-600">Loading instances...</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile || undefined} />
      
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">My Instances</h1>
              <p className="mt-1 text-sm text-gray-600">
                {totalInstances} total instances • {runningInstances} running
              </p>
            </div>
            <Link
              to="/instances/create"
              className="btn-primary inline-flex items-center"
            >
              <span className="mr-2">➕</span>
              Create Instance
            </Link>
          </div>


          {/* Error message */}
          {error && (
            <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
              {error}
            </div>
          )}

          {/* Instances */}
          {instances.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-lg shadow">
              <div className="text-gray-400 text-6xl mb-4">🖥️</div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No instances found</h3>
              <p className="text-gray-600 mb-6">
                Create your first Odoo instance to get started
              </p>
              <Link
                to="/instances/create"
                className="btn-primary inline-flex items-center"
              >
                <span className="mr-2">➕</span>
                Create Instance
              </Link>
            </div>
          ) : (
            <div className="bg-white shadow rounded-lg">
              <div className="divide-y divide-gray-200">
                {instances.map((instance) => (
                  <div key={instance.id} className="px-6 py-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center mr-4">
                          <span className="text-primary-600 font-medium">
                            {instance.name[0].toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <h4 className="text-sm font-medium text-gray-900">
                            {instance.name}
                          </h4>
                          <p className="text-sm text-gray-600">
                            {instance.description || 'No description'}
                          </p>
                          <div className="flex items-center space-x-4 mt-1">
                            <span className="text-xs text-gray-500">
                              {instance.instance_type} • {instance.odoo_version}
                            </span>
                            <span className="text-xs text-gray-500">
                              DB: {instance.database_name}
                            </span>
                            <span className="text-xs text-gray-500">
                              Created: {new Date(instance.created_at).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex items-center space-x-3">
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(instance.status)}`}>
                          {instance.status}
                        </span>
                        {/* Billing status badge */}
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                          instance.billing_status === 'paid' 
                            ? 'text-green-600 bg-green-100' 
                            : 'text-yellow-600 bg-yellow-100'
                        }`}>
                          {instance.billing_status === 'paid' ? 'Paid' : 'Trial'}
                        </span>
                        
                        {instance.external_url && (
                          <a
                            href={instance.external_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                          >
                            Open →
                          </a>
                        )}
                        
                        <div className="flex space-x-2">
                          {getActionButtons(instance)}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
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