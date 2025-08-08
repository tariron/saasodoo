import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom';
import { authAPI } from '../utils/api';

const ResetPassword: React.FC = () => {
  const { token: pathToken } = useParams<{ token: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  
  // Get token from either path parameter or query parameter
  const token = pathToken || searchParams.get('token');
  
  const [formData, setFormData] = useState({
    password: '',
    confirmPassword: '',
  });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [passwordStrength, setPasswordStrength] = useState(0);

  useEffect(() => {
    // Validate token exists
    if (!token) {
      setError('Invalid or missing reset token. Please request a new password reset.');
    }
  }, [token]);

  const checkPasswordStrength = (password: string) => {
    let strength = 0;
    const checks = {
      length: password.length >= 8,
      lowercase: /[a-z]/.test(password),
      uppercase: /[A-Z]/.test(password),
      digit: /[0-9]/.test(password),
      special: /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)
    };
    
    if (checks.length) strength++;
    if (checks.lowercase) strength++;
    if (checks.uppercase) strength++;
    if (checks.digit) strength++;
    if (checks.special) strength++;
    
    return { strength, checks };
  };

  const handlePasswordChange = (password: string) => {
    setFormData({...formData, password});
    const result = checkPasswordStrength(password);
    setPasswordStrength(result.strength);
  };

  const isPasswordValid = () => {
    const result = checkPasswordStrength(formData.password);
    const { checks } = result;
    return checks.length && checks.lowercase && checks.uppercase && checks.digit && checks.special;
  };

  const getPasswordStrengthText = () => {
    const result = checkPasswordStrength(formData.password);
    const { checks } = result;
    
    if (isPasswordValid()) {
      return 'Strong - All requirements met';
    }
    
    const missing = [];
    if (!checks.length) missing.push('8+ characters');
    if (!checks.uppercase) missing.push('uppercase letter');
    if (!checks.lowercase) missing.push('lowercase letter');  
    if (!checks.digit) missing.push('number');
    if (!checks.special) missing.push('special character');
    
    return `Missing: ${missing.join(', ')}`;
  };

  const getPasswordStrengthColor = () => {
    if (isPasswordValid()) {
      return 'bg-green-500';
    } else if (passwordStrength >= 3) {
      return 'bg-yellow-500';
    } else {
      return 'bg-red-500';
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // Client-side validation
    if (!isPasswordValid()) {
      setError('Password must contain at least 8 characters with uppercase, lowercase, digit, and special character');
      setLoading(false);
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      setLoading(false);
      return;
    }

    if (!token) {
      setError('Invalid reset token. Please request a new password reset.');
      setLoading(false);
      return;
    }

    try {
      const response = await authAPI.resetPasswordWithToken(token, formData.password, formData.confirmPassword);
      
      if (response.data.success) {
        setSuccess(true);
        // Redirect to login after 3 seconds
        setTimeout(() => {
          navigate('/login');
        }, 3000);
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 
                          err.response?.data?.message || 
                          'Password reset failed. Please try again or request a new reset link.';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: 'password' | 'confirmPassword', value: string) => {
    if (field === 'password') {
      handlePasswordChange(value);
    } else {
      setFormData(prev => ({ ...prev, [field]: value }));
    }
    
    // Clear errors when user starts typing
    if (error) setError('');
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-8">
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <svg className="h-12 w-12 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 18.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Invalid Reset Link</h2>
            <p className="text-gray-600 mb-6">
              This password reset link is invalid or has expired.
            </p>
            <div className="space-y-4">
              <Link to="/forgot-password" className="btn-primary">
                Request new reset link
              </Link>
              <Link to="/login" className="block text-primary-600 hover:text-primary-500">
                Back to sign in
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Set new password
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Enter your new password below
          </p>
        </div>

        {success ? (
          <div className="bg-green-50 border border-green-200 rounded-md p-6 text-center">
            <div className="flex justify-center mb-4">
              <svg className="h-12 w-12 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-green-800 mb-2">
              Password reset successful!
            </h3>
            <p className="text-green-700 mb-4">
              Your password has been updated successfully.
            </p>
            <p className="text-sm text-green-600">
              Redirecting you to sign in...
            </p>
          </div>
        ) : (
          <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md text-sm">
                {error}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                  New password
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={formData.password}
                  onChange={(e) => handleInputChange('password', e.target.value)}
                  className="input-field"
                  placeholder="Enter new password"
                />
                
                {formData.password && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">Password Strength:</span>
                      <span className={`font-medium ${
                        isPasswordValid() ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {getPasswordStrengthText()}
                      </span>
                    </div>
                    <div className="mt-1 w-full bg-gray-200 rounded-full h-2">
                      <div 
                        className={`h-2 rounded-full transition-all duration-300 ${getPasswordStrengthColor()}`}
                        style={{ width: `${(passwordStrength / 5) * 100}%` }}
                      ></div>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      Required: 8+ characters, uppercase, lowercase, number & special character
                    </div>
                  </div>
                )}
              </div>

              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
                  Confirm new password
                </label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={formData.confirmPassword}
                  onChange={(e) => handleInputChange('confirmPassword', e.target.value)}
                  className="input-field"
                  placeholder="Confirm new password"
                />
                
                {formData.confirmPassword && (
                  <div className="mt-1 text-xs">
                    {formData.password === formData.confirmPassword ? (
                      <span className="text-green-600">✓ Passwords match</span>
                    ) : (
                      <span className="text-red-600">✗ Passwords do not match</span>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={loading || !isPasswordValid() || formData.password !== formData.confirmPassword || !token}
                className="group relative w-full btn-primary text-sm font-medium"
              >
                {loading ? (
                  <span className="flex items-center justify-center">
                    <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Updating password...
                  </span>
                ) : (
                  'Update password'
                )}
              </button>
            </div>

            <div className="text-center">
              <p className="text-sm text-gray-600">
                Remember your password?{' '}
                <Link to="/login" className="font-medium text-primary-600 hover:text-primary-500">
                  Back to sign in
                </Link>
              </p>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default ResetPassword;