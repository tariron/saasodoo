import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { authAPI } from '../utils/api';

const Register: React.FC = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    confirm_password: '',
    company: '',
    phone: '',
    agree_terms: false
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [passwordStrength, setPasswordStrength] = useState(0);

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
    setError(null);

    // Validation
    if (formData.password !== formData.confirm_password) {
      setError('Passwords do not match');
      return;
    }

    if (!isPasswordValid()) {
      setError('Password must contain at least 8 characters with uppercase, lowercase, digit, and special character');
      return;
    }

    if (!formData.agree_terms) {
      setError('You must agree to the Terms of Service and Privacy Policy');
      return;
    }

    setLoading(true);

    try {
      const registerData = {
        first_name: formData.first_name,
        last_name: formData.last_name,
        email: formData.email,
        password: formData.password,
        accept_terms: formData.agree_terms,
        ...(formData.phone && formData.phone.trim() && { phone: formData.phone.trim() }),
        ...(formData.company && formData.company.trim() && { company: formData.company.trim() }),
      };

      const response = await authAPI.register(registerData);

      if (response.data.success) {
        alert('Registration successful! Please check your email for verification.');
        navigate('/login');
      } else {
        setError(response.data.message || 'Registration failed');
      }
    } catch (err: any) {
      console.error('Registration error:', err);
      
      let errorMessage = 'Registration failed. Please try again.';
      
      if (err.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          const validationErrors = err.response.data.detail.map((error: any) => {
            if (error.loc && error.msg) {
              const field = error.loc[error.loc.length - 1];
              return `${field}: ${error.msg}`;
            }
            return error.msg || 'Validation error';
          });
          errorMessage = validationErrors.join('. ');
        } else if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        }
      } else if (err.response?.data?.message) {
        errorMessage = err.response.data.message;
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Create your account
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Join thousands of businesses using our Odoo SaaS platform
          </p>
        </div>
        
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="first_name" className="block text-sm font-medium text-gray-700">
                First Name
              </label>
              <input
                id="first_name"
                name="first_name"
                type="text"
                required
                value={formData.first_name}
                onChange={(e) => setFormData({...formData, first_name: e.target.value})}
                className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="John"
              />
            </div>
            <div>
              <label htmlFor="last_name" className="block text-sm font-medium text-gray-700">
                Last Name
              </label>
              <input
                id="last_name"
                name="last_name"
                type="text"
                required
                value={formData.last_name}
                onChange={(e) => setFormData({...formData, last_name: e.target.value})}
                className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="Doe"
              />
            </div>
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email Address
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={formData.email}
              onChange={(e) => setFormData({...formData, email: e.target.value})}
              className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              placeholder="john@example.com"
            />
          </div>

          <div>
            <label htmlFor="company" className="block text-sm font-medium text-gray-700">
              Company (Optional)
            </label>
            <input
              id="company"
              name="company"
              type="text"
              value={formData.company}
              onChange={(e) => setFormData({...formData, company: e.target.value})}
              className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              placeholder="Your Company Inc."
            />
          </div>

          <div>
            <label htmlFor="phone" className="block text-sm font-medium text-gray-700">
              Phone Number (Optional)
            </label>
            <input
              id="phone"
              name="phone"
              type="tel"
              value={formData.phone}
              onChange={(e) => setFormData({...formData, phone: e.target.value})}
              className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              placeholder="+1234567890"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              value={formData.password}
              onChange={(e) => handlePasswordChange(e.target.value)}
              className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              placeholder="Enter a strong password"
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
            <label htmlFor="confirm_password" className="block text-sm font-medium text-gray-700">
              Confirm Password
            </label>
            <input
              id="confirm_password"
              name="confirm_password"
              type="password"
              autoComplete="new-password"
              required
              value={formData.confirm_password}
              onChange={(e) => setFormData({...formData, confirm_password: e.target.value})}
              className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              placeholder="Confirm your password"
            />
            
            {formData.confirm_password && (
              <div className="mt-1 text-xs">
                {formData.password === formData.confirm_password ? (
                  <span className="text-green-600">✓ Passwords match</span>
                ) : (
                  <span className="text-red-600">✗ Passwords do not match</span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center">
            <input
              id="agree_terms"
              name="agree_terms"
              type="checkbox"
              checked={formData.agree_terms}
              onChange={(e) => setFormData({...formData, agree_terms: e.target.checked})}
              className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            />
            <label htmlFor="agree_terms" className="ml-2 block text-sm text-gray-900">
              I agree to the{' '}
              <button 
                type="button"
                onClick={() => window.open('/terms', '_blank')}
                className="text-blue-600 hover:text-blue-500 underline"
              >
                Terms of Service
              </button>{' '}
              and{' '}
              <button 
                type="button"
                onClick={() => window.open('/privacy', '_blank')}
                className="text-blue-600 hover:text-blue-500 underline"
              >
                Privacy Policy
              </button>
            </label>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading || !isPasswordValid() || !formData.agree_terms}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Creating Account...
                </span>
              ) : (
                'Create Account'
              )}
            </button>
          </div>

          <div className="text-center">
            <span className="text-sm text-gray-600">
              Already have an account?{' '}
              <Link to="/login" className="font-medium text-blue-600 hover:text-blue-500">
                Sign in here
              </Link>
            </span>
          </div>
        </form>

        <div className="mt-8 border-t border-gray-200 pt-8">
          <h3 className="text-lg font-medium text-gray-900 text-center mb-4">
            Why choose our platform?
          </h3>
          <div className="grid grid-cols-1 gap-4 text-sm text-gray-600">
            <div className="flex items-center">
              <span className="text-green-500 mr-2">✓</span>
              14-day free trial, no credit card required
            </div>
            <div className="flex items-center">
              <span className="text-green-500 mr-2">✓</span>
              Fully managed Odoo instances
            </div>
            <div className="flex items-center">
              <span className="text-green-500 mr-2">✓</span>
              Automatic backups and updates
            </div>
            <div className="flex items-center">
              <span className="text-green-500 mr-2">✓</span>
              24/7 technical support
            </div>
            <div className="flex items-center">
              <span className="text-green-500 mr-2">✓</span>
              Scale as you grow
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Register;