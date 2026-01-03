import React, { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';

const LandingPage: React.FC = () => {
  const featuresRef = useRef<HTMLDivElement>(null);

  // Scroll to features section if hash is #features
  useEffect(() => {
    if (window.location.hash === '#features' && featuresRef.current) {
      featuresRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, []);

  const features = [
    {
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      title: 'Deploy in Minutes',
      description: 'Launch your Odoo instance with a single click. No server setup, no configuration headaches.',
      color: 'primary',
    },
    {
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
      title: 'Enterprise Security',
      description: 'SOC 2 compliant infrastructure with automatic backups, encryption, and 99.9% uptime guarantee.',
      color: 'accent',
    },
    {
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ),
      title: 'Auto-Scaling',
      description: 'Your instance grows with your business. Upgrade resources instantly without downtime.',
      color: 'primary',
    },
    {
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
      title: 'Dedicated Support',
      description: '24/7 expert support from Odoo specialists. We handle the technical, you focus on business.',
      color: 'accent',
    },
  ];

  const testimonials = [
    {
      quote: "SaaSodoo transformed our operations. We deployed a full ERP in 10 minutes instead of 10 weeks.",
      author: "Sarah Chen",
      role: "CTO, TechFlow Inc.",
      avatar: "SC",
    },
    {
      quote: "The best decision we made. Zero maintenance headaches and their support team is incredible.",
      author: "Michael Torres",
      role: "Operations Director, Retail Plus",
      avatar: "MT",
    },
    {
      quote: "Finally, enterprise ERP without the enterprise price tag. Our ROI was positive in month one.",
      author: "Emma Williams",
      role: "CEO, StartupXYZ",
      avatar: "EW",
    },
  ];

  const plans = [
    { name: 'Basic', price: 9, description: 'Perfect for small teams', popular: false },
    { name: 'Standard', price: 19, description: 'For growing businesses', popular: true },
    { name: 'Premium', price: 39, description: 'Maximum power & support', popular: false },
  ];

  const stats = [
    { value: '10K+', label: 'Active Instances' },
    { value: '99.9%', label: 'Uptime SLA' },
    { value: '<60s', label: 'Deploy Time' },
    { value: '24/7', label: 'Expert Support' },
  ];

  return (
    <div className="overflow-hidden">
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center pt-20 lg:pt-0">
        {/* Background decorations */}
        <div className="absolute inset-0 bg-hero-pattern opacity-50" />
        <div className="absolute top-20 right-0 w-1/2 h-1/2 bg-gradient-radial from-primary-500/10 via-transparent to-transparent" />
        <div className="absolute bottom-0 left-0 w-1/3 h-1/3 bg-gradient-radial from-accent-500/10 via-transparent to-transparent" />

        {/* Floating geometric shapes */}
        <div className="absolute top-1/4 right-1/4 w-20 h-20 border-2 border-primary-200 rounded-2xl rotate-12 animate-pulse-soft opacity-60" />
        <div className="absolute bottom-1/3 left-1/6 w-16 h-16 bg-accent-100 rounded-xl -rotate-12 animate-pulse-soft opacity-40" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/3 left-1/4 w-12 h-12 border-2 border-accent-200 rounded-full animate-pulse-soft opacity-50" style={{ animationDelay: '0.5s' }} />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 lg:py-32 relative">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
            {/* Left Column - Copy */}
            <div className="text-center lg:text-left">
              {/* Badge */}
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary-50 border border-primary-100 rounded-full text-primary-700 text-sm font-medium mb-8 animate-fade-in-down">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
                </span>
                Now with 14-day free trial
              </div>

              {/* Headline */}
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-warm-900 leading-tight animate-fade-in-up">
                Your Odoo ERP,
                <span className="block mt-2">
                  <span className="text-gradient">Ready in Minutes</span>
                </span>
              </h1>

              {/* Subheadline */}
              <p className="mt-6 text-lg sm:text-xl text-warm-600 max-w-xl mx-auto lg:mx-0 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
                Deploy enterprise-grade Odoo instances without the infrastructure headache.
                Fully managed, auto-scaling, and backed by expert support.
              </p>

              {/* CTAs */}
              <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center lg:justify-start animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
                <Link
                  to="/register"
                  className="btn-primary text-base px-8 py-4 shadow-glow"
                >
                  Start Free Trial
                  <svg className="w-5 h-5 ml-2 -mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </Link>
                <Link
                  to="/pricing"
                  className="btn-secondary text-base px-8 py-4"
                >
                  View Pricing
                </Link>
              </div>

              {/* Social proof mini */}
              <div className="mt-12 flex items-center justify-center lg:justify-start gap-6 animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
                <div className="flex -space-x-3">
                  {['bg-primary-500', 'bg-accent-500', 'bg-emerald-500', 'bg-violet-500'].map((color, i) => (
                    <div
                      key={i}
                      className={`w-10 h-10 ${color} rounded-full border-2 border-white flex items-center justify-center text-white text-xs font-bold`}
                    >
                      {['JD', 'AK', 'MR', 'SC'][i]}
                    </div>
                  ))}
                </div>
                <div className="text-left">
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <svg key={star} className="w-4 h-4 text-accent-500" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                    ))}
                  </div>
                  <p className="text-sm text-warm-500">Loved by 10,000+ businesses</p>
                </div>
              </div>
            </div>

            {/* Right Column - Visual */}
            <div className="relative animate-fade-in" style={{ animationDelay: '0.2s' }}>
              {/* Main card */}
              <div className="relative bg-white rounded-3xl shadow-soft-lg border border-warm-100 p-6 lg:p-8">
                {/* Browser chrome */}
                <div className="flex items-center gap-2 mb-6">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-rose-400" />
                    <div className="w-3 h-3 rounded-full bg-amber-400" />
                    <div className="w-3 h-3 rounded-full bg-emerald-400" />
                  </div>
                  <div className="flex-1 bg-warm-100 rounded-lg px-4 py-1.5 text-sm text-warm-500 font-mono">
                    your-company.saasodoo.com
                  </div>
                </div>

                {/* Dashboard preview */}
                <div className="space-y-4">
                  {/* Stats row */}
                  <div className="grid grid-cols-3 gap-4">
                    {[
                      { label: 'Revenue', value: '$124,500', change: '+12%' },
                      { label: 'Orders', value: '1,247', change: '+8%' },
                      { label: 'Customers', value: '856', change: '+23%' },
                    ].map((stat, i) => (
                      <div key={i} className="bg-warm-50 rounded-xl p-4">
                        <p className="text-xs text-warm-500">{stat.label}</p>
                        <p className="text-lg font-bold text-warm-900 mt-1">{stat.value}</p>
                        <span className="text-xs text-emerald-600 font-medium">{stat.change}</span>
                      </div>
                    ))}
                  </div>

                  {/* Chart placeholder */}
                  <div className="bg-gradient-to-br from-primary-50 to-accent-50 rounded-xl p-6 h-40 flex items-end justify-between gap-2">
                    {[40, 65, 45, 80, 55, 90, 70, 85, 60, 95, 75, 88].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-gradient-to-t from-primary-500 to-primary-400 rounded-t-sm opacity-80"
                        style={{ height: `${h}%` }}
                      />
                    ))}
                  </div>

                  {/* Table preview */}
                  <div className="space-y-2">
                    {[
                      { id: 'SO-2024-001', customer: 'Acme Corp', amount: '$4,500' },
                      { id: 'SO-2024-002', customer: 'TechStart', amount: '$2,800' },
                    ].map((row, i) => (
                      <div key={i} className="flex items-center justify-between bg-warm-50 rounded-lg px-4 py-3">
                        <span className="text-sm font-mono text-primary-600">{row.id}</span>
                        <span className="text-sm text-warm-600">{row.customer}</span>
                        <span className="text-sm font-semibold text-warm-900">{row.amount}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Floating badge */}
              <div className="absolute -bottom-6 -left-6 bg-white rounded-2xl shadow-soft-lg border border-warm-100 p-4 flex items-center gap-3 animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
                <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-warm-900">Instance Ready</p>
                  <p className="text-xs text-warm-500">Deployed in 47 seconds</p>
                </div>
              </div>

              {/* Floating notification */}
              <div className="absolute -top-4 -right-4 bg-white rounded-2xl shadow-soft-lg border border-warm-100 p-4 flex items-center gap-3 animate-fade-in-up" style={{ animationDelay: '0.5s' }}>
                <div className="w-10 h-10 bg-primary-100 rounded-xl flex items-center justify-center">
                  <svg className="w-5 h-5 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-warm-900">Auto-backup complete</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16 bg-warm-900 relative overflow-hidden">
        <div className="absolute inset-0 bg-hero-pattern opacity-10" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {stats.map((stat, i) => (
              <div key={i} className="text-center">
                <div className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-2">
                  {stat.value}
                </div>
                <div className="text-warm-400 text-sm sm:text-base">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section ref={featuresRef} id="features" className="py-20 lg:py-32 scroll-mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Section header */}
          <div className="text-center max-w-3xl mx-auto mb-16 lg:mb-20">
            <span className="inline-block px-4 py-1.5 bg-primary-50 text-primary-700 rounded-full text-sm font-medium mb-4">
              Features
            </span>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-warm-900">
              Everything you need to run{' '}
              <span className="text-gradient">your business</span>
            </h2>
            <p className="mt-6 text-lg text-warm-600">
              Get the full power of Odoo ERP without the complexity. We handle the infrastructure so you can focus on growth.
            </p>
          </div>

          {/* Features grid */}
          <div className="grid md:grid-cols-2 gap-8 lg:gap-12">
            {features.map((feature, i) => (
              <div
                key={i}
                className="group relative bg-white rounded-2xl border border-warm-100 p-8 shadow-soft hover:shadow-soft-lg hover:border-warm-200 transition-all duration-300"
              >
                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-6 transition-transform duration-300 group-hover:scale-110 ${
                  feature.color === 'primary'
                    ? 'bg-primary-50 text-primary-600'
                    : 'bg-accent-50 text-accent-600'
                }`}>
                  {feature.icon}
                </div>
                <h3 className="text-xl font-bold text-warm-900 mb-3">
                  {feature.title}
                </h3>
                <p className="text-warm-600 leading-relaxed">
                  {feature.description}
                </p>
                {/* Decorative corner */}
                <div className={`absolute top-0 right-0 w-24 h-24 rounded-tr-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 ${
                  feature.color === 'primary'
                    ? 'bg-gradient-to-bl from-primary-50 to-transparent'
                    : 'bg-gradient-to-bl from-accent-50 to-transparent'
                }`} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials Section */}
      <section className="py-20 lg:py-32 bg-gradient-to-b from-warm-50 to-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Section header */}
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="inline-block px-4 py-1.5 bg-accent-50 text-accent-700 rounded-full text-sm font-medium mb-4">
              Testimonials
            </span>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-warm-900">
              Trusted by businesses{' '}
              <span className="text-gradient">worldwide</span>
            </h2>
          </div>

          {/* Testimonials grid */}
          <div className="grid md:grid-cols-3 gap-8">
            {testimonials.map((testimonial, i) => (
              <div
                key={i}
                className="bg-white rounded-2xl border border-warm-100 p-8 shadow-soft hover:shadow-soft-lg transition-shadow duration-300"
              >
                {/* Stars */}
                <div className="flex gap-1 mb-6">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <svg key={star} className="w-5 h-5 text-accent-500" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                  ))}
                </div>

                {/* Quote */}
                <blockquote className="text-warm-700 leading-relaxed mb-6">
                  "{testimonial.quote}"
                </blockquote>

                {/* Author */}
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-gradient-to-br from-primary-400 to-primary-600 rounded-full flex items-center justify-center text-white font-bold">
                    {testimonial.avatar}
                  </div>
                  <div>
                    <div className="font-semibold text-warm-900">{testimonial.author}</div>
                    <div className="text-sm text-warm-500">{testimonial.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Preview Section */}
      <section className="py-20 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Section header */}
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="inline-block px-4 py-1.5 bg-primary-50 text-primary-700 rounded-full text-sm font-medium mb-4">
              Pricing
            </span>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-warm-900">
              Simple, transparent{' '}
              <span className="text-gradient">pricing</span>
            </h2>
            <p className="mt-6 text-lg text-warm-600">
              Start with a 14-day free trial. No credit card required.
            </p>
          </div>

          {/* Pricing cards */}
          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {plans.map((plan, i) => (
              <div
                key={i}
                className={`relative bg-white rounded-2xl border p-8 transition-all duration-300 hover:-translate-y-1 ${
                  plan.popular
                    ? 'border-primary-200 shadow-glow'
                    : 'border-warm-100 shadow-soft hover:shadow-soft-lg'
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-primary-500 to-primary-600 text-white text-sm font-medium rounded-full">
                    Most Popular
                  </div>
                )}

                <div className="text-center mb-8">
                  <h3 className="text-xl font-bold text-warm-900 mb-2">{plan.name}</h3>
                  <p className="text-warm-500 text-sm">{plan.description}</p>
                  <div className="mt-6">
                    <span className="text-4xl font-bold text-warm-900">${plan.price}</span>
                    <span className="text-warm-500">/month</span>
                  </div>
                </div>

                <Link
                  to="/register"
                  className={`block text-center py-3 px-6 rounded-xl font-semibold transition-all duration-200 ${
                    plan.popular
                      ? 'btn-primary'
                      : 'bg-warm-100 text-warm-700 hover:bg-warm-200'
                  }`}
                >
                  Start Free Trial
                </Link>
              </div>
            ))}
          </div>

          {/* Link to full pricing */}
          <div className="text-center mt-12">
            <Link
              to="/pricing"
              className="inline-flex items-center gap-2 text-primary-600 font-medium hover:text-primary-700 transition-colors"
            >
              Compare all features
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </Link>
          </div>
        </div>
      </section>

      {/* Final CTA Section */}
      <section className="py-20 lg:py-32 bg-warm-900 relative overflow-hidden">
        {/* Background decorations */}
        <div className="absolute inset-0 bg-hero-pattern opacity-10" />
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-accent-500/10 rounded-full blur-3xl" />

        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center relative">
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-6">
            Ready to transform your business?
          </h2>
          <p className="text-lg text-warm-300 mb-10 max-w-2xl mx-auto">
            Join thousands of businesses running their operations on SaaSodoo.
            Start your free trial today — no credit card required.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/register"
              className="btn-accent text-base px-8 py-4"
            >
              Start Your Free Trial
              <svg className="w-5 h-5 ml-2 -mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </Link>
            <Link
              to="/pricing"
              className="inline-flex items-center justify-center px-8 py-4 text-white font-semibold rounded-xl border border-warm-700 hover:bg-warm-800 transition-colors duration-200"
            >
              View Pricing
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LandingPage;
