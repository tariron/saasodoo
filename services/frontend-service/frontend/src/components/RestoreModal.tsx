import React, { useState, useEffect } from 'react';
import { instanceAPI, Instance } from '../utils/api';

interface Backup {
  backup_id: string;
  backup_name: string;
  instance_name: string;
  created_at: string;
  database_size: number;
  data_size: number;
  total_size: number;
  odoo_version: string;
  status: string;
}

interface BackupsResponse {
  instance_id: string;
  instance_name: string;
  backups: Backup[];
  total_backups: number;
}

interface RestoreModalProps {
  instance: Instance;
  isOpen: boolean;
  onClose: () => void;
  onRestore: (instanceId: string, backupId: string) => Promise<void>;
}

const RestoreModal: React.FC<RestoreModalProps> = ({ instance, isOpen, onClose, onRestore }) => {
  const [backups, setBackups] = useState<Backup[]>([]);
  const [selectedBackup, setSelectedBackup] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState<'select' | 'confirm'>('select');
  const [createBackupFirst, setCreateBackupFirst] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchBackups();
      setStep('select');
      setSelectedBackup(null);
      setError('');
    }
  }, [isOpen, instance.id]);

  const fetchBackups = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await instanceAPI.backups(instance.id);
      const data: BackupsResponse = response.data;
      setBackups(data.backups || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch backups');
      setBackups([]);
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatRelativeTime = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMinutes < 60) {
      return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
      return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    } else if (diffDays < 30) {
      return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  const handleSelectBackup = (backupId: string) => {
    setSelectedBackup(backupId);
    setStep('confirm');
  };

  const handleConfirmRestore = async () => {
    if (!selectedBackup) return;

    try {
      setRestoring(true);
      setError('');

      // Optionally create backup first
      if (createBackupFirst) {
        await instanceAPI.action(instance.id, 'backup', { 
          name: `pre_restore_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}` 
        });
      }

      // Perform restore
      await onRestore(instance.id, selectedBackup);
      onClose();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Restore failed');
    } finally {
      setRestoring(false);
    }
  };

  const handleClose = () => {
    if (!restoring) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const selectedBackupData = backups.find(b => b.backup_id === selectedBackup);

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b">
          <h3 className="text-lg font-medium text-gray-900">
            Restore Instance: {instance.name}
          </h3>
          <button
            onClick={handleClose}
            disabled={restoring}
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Warning Banner */}
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-md">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">
                Warning: This will replace ALL current data
              </h3>
              <div className="mt-2 text-sm text-red-700">
                <p>Restoring a backup will permanently replace all current instance data with the backup data. This action cannot be undone.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="mt-6">
          {step === 'select' && (
            <>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <svg className="animate-spin h-8 w-8 text-primary-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span className="ml-2 text-gray-600">Loading backups...</span>
                </div>
              ) : error ? (
                <div className="text-center py-8">
                  <div className="text-red-600 mb-4">{error}</div>
                  <button
                    onClick={fetchBackups}
                    className="btn-secondary"
                  >
                    Retry
                  </button>
                </div>
              ) : backups.length === 0 ? (
                <div className="text-center py-8">
                  <div className="text-gray-400 text-4xl mb-4">📦</div>
                  <h3 className="text-lg font-medium text-gray-900 mb-2">No backups available</h3>
                  <p className="text-gray-600">
                    This instance has no backups to restore from. Create a backup first.
                  </p>
                </div>
              ) : (
                <>
                  <h4 className="text-md font-medium text-gray-900 mb-4">
                    Select a backup to restore ({backups.length} available)
                  </h4>
                  <div className="space-y-3 max-h-64 overflow-y-auto">
                    {backups.map((backup) => (
                      <div
                        key={backup.backup_id}
                        onClick={() => handleSelectBackup(backup.backup_id)}
                        className="p-4 border border-gray-200 rounded-lg hover:border-primary-300 hover:bg-primary-50 cursor-pointer transition-colors"
                      >
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <h5 className="font-medium text-gray-900">{backup.backup_name}</h5>
                            <div className="mt-1 space-y-1">
                              <p className="text-sm text-gray-600">
                                Created: {formatRelativeTime(backup.created_at)} 
                                <span className="text-gray-400 ml-2">
                                  ({new Date(backup.created_at).toLocaleString()})
                                </span>
                              </p>
                              <p className="text-sm text-gray-600">
                                Size: {formatFileSize(backup.total_size)} • Odoo {backup.odoo_version}
                              </p>
                              <div className="flex items-center">
                                <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                  backup.status === 'completed' 
                                    ? 'bg-green-100 text-green-800' 
                                    : 'bg-yellow-100 text-yellow-800'
                                }`}>
                                  {backup.status}
                                </span>
                              </div>
                            </div>
                          </div>
                          <div className="text-primary-600">
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}

          {step === 'confirm' && selectedBackupData && (
            <div>
              <h4 className="text-md font-medium text-gray-900 mb-4">
                Confirm Restore
              </h4>
              
              {/* Selected backup info */}
              <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg mb-4">
                <h5 className="font-medium text-gray-900 mb-2">Selected Backup:</h5>
                <div className="space-y-1 text-sm text-gray-600">
                  <p><strong>Name:</strong> {selectedBackupData.backup_name}</p>
                  <p><strong>Created:</strong> {formatRelativeTime(selectedBackupData.created_at)}</p>
                  <p><strong>Size:</strong> {formatFileSize(selectedBackupData.total_size)}</p>
                  <p><strong>Odoo Version:</strong> {selectedBackupData.odoo_version}</p>
                </div>
              </div>

              {/* Current instance info */}
              <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg mb-4">
                <h5 className="font-medium text-gray-900 mb-2">Current Instance Data (will be replaced):</h5>
                <div className="space-y-1 text-sm text-gray-600">
                  <p><strong>Instance:</strong> {instance.name}</p>
                  <p><strong>Status:</strong> {instance.status}</p>
                  <p><strong>Last Updated:</strong> {formatRelativeTime(instance.updated_at)}</p>
                  <p><strong>Odoo Version:</strong> {instance.odoo_version}</p>
                </div>
              </div>

              {/* Backup option */}
              <div className="mb-4">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={createBackupFirst}
                    onChange={(e) => setCreateBackupFirst(e.target.checked)}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                  />
                  <span className="ml-2 text-sm text-gray-700">
                    Create backup of current data before restore (recommended)
                  </span>
                </label>
              </div>

              {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-md text-sm">
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-6 pt-4 border-t flex justify-end space-x-3">
          {step === 'select' ? (
            <button
              onClick={handleClose}
              disabled={restoring}
              className="btn-secondary"
            >
              Cancel
            </button>
          ) : (
            <>
              <button
                onClick={() => setStep('select')}
                disabled={restoring}
                className="btn-secondary"
              >
                Back
              </button>
              <button
                onClick={handleConfirmRestore}
                disabled={restoring || !selectedBackup}
                className="btn-primary bg-red-600 hover:bg-red-700"
              >
                {restoring ? (
                  <span className="flex items-center">
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    {createBackupFirst ? 'Creating Backup & Restoring...' : 'Restoring...'}
                  </span>
                ) : (
                  `Confirm Restore${createBackupFirst ? ' (with backup)' : ''}`
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default RestoreModal;