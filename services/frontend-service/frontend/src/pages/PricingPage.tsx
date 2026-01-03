import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { BillingPeriod, BILLING_PERIOD_LABELS } from '../types/billing';

const PricingPage: React.FC = () => {
  const [billingPeriod, setBillingPeriod] = useState<BillingPeriod>('MONTHLY');
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  // Pricing data with all billing periods
  const plans = [
    {
      name: 'Basic',
      description: 'Perfect for small teams getting started',
      prices: {
        MONTHLY: 9,
        QUARTERLY: 25,
        BIANNUAL: 49,
        ANNUAL: 89,
      },
      savings: {
        QUARTERLY: 7,
        BIANNUAL: 9,
        ANNUAL: 18,
      },
      features: [
        { name: '1 Odoo Instance', included: true },
        { name: '1 CPU Core', included: true },
        { name: '2 GB RAM', included: true },
        { name: '10 GB Storage', included: true },
        { name: 'Daily Backups', included: true },
        { name: 'SSL Certificate', included: true },
        { name: 'Email Support', included: true },
        { name: 'Custom Domain', included: false },
        { name: 'Priority Support', included: false },
        { name: 'Dedicated Database', included: false },
      ],
      cta: 'Start Free Trial',
      popular: false,
      trial: true,
    },
    {
      name: 'Standard',
      description: 'For growing businesses that need more power',
      prices: {
        MONTHLY: 19,
        QUARTERLY: 49,
        BIANNUAL: 99,
        ANNUAL: 179,
      },
      savings: {
        QUARTERLY: 14,
        BIANNUAL: 13,
        ANNUAL: 21,
      },
      features: [
        { name: '1 Odoo Instance', included: true },
        { name: '2 CPU Cores', included: true },
        { name: '4 GB RAM', included: true },
        { name: '20 GB Storage', included: true },
        { name: 'Daily Backups', included: true },
        { name: 'SSL Certificate', included: true },
        { name: 'Email & Chat Support', included: true },
        { name: 'Custom Domain', included: true },
        { name: 'Priority Support', included: false },
        { name: 'Dedicated Database', included: false },
      ],
      cta: 'Get Started',
      popular: true,
      trial: false,
    },
    {
      name: 'Premium',
      description: 'Maximum power for demanding workloads',
      prices: {
        MONTHLY: 39,
        QUARTERLY: 99,
        BIANNUAL: 199,
        ANNUAL: 379,
      },
      savings: {
        QUARTERLY: 15,
        BIANNUAL: 15,
        ANNUAL: 19,
      },
      features: [
        { name: '1 Odoo Instance', included: true },
        { name: '4 CPU Cores', included: true },
        { name: '8 GB RAM', included: true },
        { name: '50 GB Storage', included: true },
        { name: 'Hourly Backups', included: true },
        { name: 'SSL Certificate', included: true },
        { name: '24/7 Phone Support', included: true },
        { name: 'Custom Domain', included: true },
        { name: 'Priority Support', included: true },
        { name: 'Dedicated Database', included: true },
      ],
      cta: 'Get Started',
      popular: false,
      trial: false,
    },
  ];

  const faqs = [
    {
      question: 'How does the 14-day free trial work?',
      answer: 'You can start a free trial on the Basic plan without a credit card. After 14 days, you\'ll be prompted to enter payment details to continue. Your data and configuration will be preserved.',
    },
    {
      question: 'Can I upgrade or downgrade my plan?',
      answer: 'Yes! You can upgrade or downgrade at any time. When upgrading, you\'ll be charged a prorated amount. When downgrading, the new rate applies at your next billing cycle.',
    },
    {
      question: 'What payment methods do you accept?',
      answer: 'We accept all major credit cards, EcoCash, OneMoney, and bank transfers for annual plans. All payments are processed securely.',
    },
    {
      question: 'Is there a setup fee?',
      answer: 'No, there are no setup fees or hidden costs. You only pay the advertised price for your chosen plan.',
    },
    {
      question: 'What happens to my data if I cancel?',
      answer: 'If you cancel, your data is retained for 30 days. During this period, you can reactivate your account or export your data. After 30 days, data is permanently deleted.',
    },
    {
      question: 'Do you offer custom enterprise plans?',
      answer: 'Yes! For larger organizations or specific requirements, contact our sales team for a custom quote with dedicated resources and SLA guarantees.',
    },
  ];

  const billingPeriods: BillingPeriod[] = ['MONTHLY', 'QUARTERLY', 'BIANNUAL', 'ANNUAL'];

  const getMonthlyEquivalent = (price: number, period: BillingPeriod): string => {
    const months: Record<BillingPeriod, number> = {
      MONTHLY: 1,
      QUARTERLY: 3,
      BIANNUAL: 6,
      ANNUAL: 12,
    };
    return (price / months[period]).toFixed(2);
  };

  const getPeriodLabel = (period: BillingPeriod): string => {
    const labels: Record<BillingPeriod, string> = {
      MONTHLY: '/mo',
      QUARTERLY: '/qtr',
      BIANNUAL: '/6mo',
      ANNUAL: '/yr',
    };
    return labels[period];
  };

  return (
    <div className="pt-20">
      {/* Hero Section */}
      <section className="py-16 lg:py-24 relative overflow-hidden">
        {/* Background decorations */}
        <div className="absolute top-0 right-0 w-1/2 h-1/2 bg-gradient-radial from-primary-500/10 via-transparent to-transparent" />
        <div className="absolute bottom-0 left-0 w-1/3 h-1/3 bg-gradient-radial from-accent-500/10 via-transparent to-transparent" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
          <div className="text-center max-w-3xl mx-auto">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-warm-900 animate-fade-in-up">
              Simple, transparent{' '}
              <span className="text-gradient">pricing</span>
            </h1>
            <p className="mt-6 text-lg sm:text-xl text-warm-600 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
              Choose the plan that fits your business. All plans include a fully-managed Odoo instance with automatic backups and updates.
            </p>
          </div>

          {/* Billing Period Toggle */}
          <div className="mt-12 flex justify-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <div className="inline-flex items-center p-1.5 bg-warm-100 rounded-2xl">
              {billingPeriods.map((period) => (
                <button
                  key={period}
                  onClick={() => setBillingPeriod(period)}
                  className={`relative px-4 sm:px-6 py-2.5 text-sm font-medium rounded-xl transition-all duration-200 ${
                    billingPeriod === period
                      ? 'bg-white text-warm-900 shadow-soft'
                      : 'text-warm-600 hover:text-warm-900'
                  }`}
                >
                  {BILLING_PERIOD_LABELS[period]}
                  {period !== 'MONTHLY' && billingPeriod === period && (
                    <span className="absolute -top-2 -right-2 px-1.5 py-0.5 bg-emerald-500 text-white text-xs font-bold rounded-full">
                      Save
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Annual savings note */}
          {billingPeriod !== 'MONTHLY' && (
            <p className="mt-4 text-center text-sm text-emerald-600 font-medium animate-fade-in">
              Save up to 21% with {BILLING_PERIOD_LABELS[billingPeriod].toLowerCase()} billing
            </p>
          )}
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-20 lg:pb-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-3 gap-8">
            {plans.map((plan, i) => (
              <div
                key={i}
                className={`relative bg-white rounded-3xl border-2 transition-all duration-300 hover:-translate-y-1 ${
                  plan.popular
                    ? 'border-primary-300 shadow-glow'
                    : 'border-warm-100 shadow-soft hover:shadow-soft-lg hover:border-warm-200'
                }`}
              >
                {/* Popular badge */}
                {plan.popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                    <div className="px-4 py-1.5 bg-gradient-to-r from-primary-500 to-primary-600 text-white text-sm font-semibold rounded-full shadow-glow">
                      Most Popular
                    </div>
                  </div>
                )}

                {/* Trial badge */}
                {plan.trial && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                    <div className="px-4 py-1.5 bg-gradient-to-r from-accent-500 to-accent-600 text-white text-sm font-semibold rounded-full">
                      14-Day Free Trial
                    </div>
                  </div>
                )}

                <div className="p-8">
                  {/* Plan header */}
                  <div className="text-center mb-8">
                    <h3 className="text-2xl font-bold text-warm-900">{plan.name}</h3>
                    <p className="mt-2 text-warm-500">{plan.description}</p>
                  </div>

                  {/* Price */}
                  <div className="text-center mb-8">
                    <div className="flex items-baseline justify-center gap-1">
                      <span className="text-5xl font-bold text-warm-900">
                        ${plan.prices[billingPeriod]}
                      </span>
                      <span className="text-warm-500 text-lg">
                        {getPeriodLabel(billingPeriod)}
                      </span>
                    </div>

                    {/* Monthly equivalent for non-monthly */}
                    {billingPeriod !== 'MONTHLY' && (
                      <div className="mt-2 space-y-1">
                        <p className="text-sm text-warm-500">
                          ${getMonthlyEquivalent(plan.prices[billingPeriod], billingPeriod)}/mo equivalent
                        </p>
                        {plan.savings[billingPeriod as keyof typeof plan.savings] && (
                          <span className="inline-block px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs font-semibold rounded-full">
                            Save {plan.savings[billingPeriod as keyof typeof plan.savings]}%
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* CTA Button */}
                  <Link
                    to="/register"
                    className={`block text-center py-4 px-6 rounded-xl font-semibold transition-all duration-200 ${
                      plan.popular
                        ? 'btn-primary'
                        : 'bg-warm-100 text-warm-700 hover:bg-warm-200'
                    }`}
                  >
                    {plan.cta}
                  </Link>

                  {/* Features list */}
                  <div className="mt-8 pt-8 border-t border-warm-100">
                    <p className="text-sm font-semibold text-warm-900 mb-4">What's included:</p>
                    <ul className="space-y-3">
                      {plan.features.map((feature, j) => (
                        <li key={j} className="flex items-start gap-3">
                          {feature.included ? (
                            <svg className="w-5 h-5 text-primary-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          ) : (
                            <svg className="w-5 h-5 text-warm-300 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          )}
                          <span className={feature.included ? 'text-warm-700' : 'text-warm-400'}>
                            {feature.name}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Enterprise callout */}
          <div className="mt-16 bg-gradient-to-r from-warm-900 to-warm-800 rounded-3xl p-8 lg:p-12 text-center relative overflow-hidden">
            {/* Background decoration */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-primary-500/10 rounded-full blur-3xl" />
            <div className="absolute bottom-0 left-0 w-48 h-48 bg-accent-500/10 rounded-full blur-3xl" />

            <div className="relative">
              <h3 className="text-2xl lg:text-3xl font-bold text-white mb-4">
                Need a custom enterprise solution?
              </h3>
              <p className="text-warm-300 mb-8 max-w-2xl mx-auto">
                Get dedicated resources, custom SLAs, and white-glove onboarding for your organization.
              </p>
              <a
                href="mailto:enterprise@saasodoo.com"
                className="inline-flex items-center gap-2 btn-accent"
              >
                Contact Sales
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                </svg>
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Comparison Table */}
      <section className="py-20 lg:py-32 bg-warm-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold text-warm-900">
              Compare all features
            </h2>
            <p className="mt-4 text-lg text-warm-600">
              See exactly what you get with each plan
            </p>
          </div>

          {/* Desktop table */}
          <div className="hidden lg:block bg-white rounded-2xl shadow-soft border border-warm-100 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-warm-100">
                  <th className="text-left p-6 text-warm-900 font-semibold">Feature</th>
                  {plans.map((plan) => (
                    <th key={plan.name} className="p-6 text-center">
                      <div className="text-lg font-bold text-warm-900">{plan.name}</div>
                      <div className="text-sm text-warm-500">${plan.prices.MONTHLY}/mo</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { name: 'CPU Cores', values: ['1 Core', '2 Cores', '4 Cores'] },
                  { name: 'RAM', values: ['2 GB', '4 GB', '8 GB'] },
                  { name: 'Storage', values: ['10 GB', '20 GB', '50 GB'] },
                  { name: 'Backup Frequency', values: ['Daily', 'Daily', 'Hourly'] },
                  { name: 'Custom Domain', values: [false, true, true] },
                  { name: 'SSL Certificate', values: [true, true, true] },
                  { name: 'Support', values: ['Email', 'Email & Chat', '24/7 Phone'] },
                  { name: 'Priority Support', values: [false, false, true] },
                  { name: 'Dedicated Database', values: [false, false, true] },
                  { name: 'API Access', values: [true, true, true] },
                  { name: 'Uptime SLA', values: ['99%', '99.5%', '99.9%'] },
                ].map((row, i) => (
                  <tr key={i} className={i % 2 === 0 ? 'bg-warm-50/50' : ''}>
                    <td className="p-6 text-warm-700 font-medium">{row.name}</td>
                    {row.values.map((value, j) => (
                      <td key={j} className="p-6 text-center">
                        {typeof value === 'boolean' ? (
                          value ? (
                            <svg className="w-6 h-6 text-primary-500 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          ) : (
                            <svg className="w-6 h-6 text-warm-300 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          )
                        ) : (
                          <span className="text-warm-700">{value}</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="lg:hidden space-y-4">
            {plans.map((plan) => (
              <details key={plan.name} className="bg-white rounded-xl border border-warm-100 shadow-soft group">
                <summary className="flex items-center justify-between p-6 cursor-pointer">
                  <div>
                    <h3 className="font-bold text-warm-900">{plan.name}</h3>
                    <p className="text-sm text-warm-500">${plan.prices.MONTHLY}/month</p>
                  </div>
                  <svg className="w-5 h-5 text-warm-400 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div className="px-6 pb-6 pt-2 border-t border-warm-100">
                  <ul className="space-y-2">
                    {plan.features.map((feature, j) => (
                      <li key={j} className="flex items-center gap-2">
                        {feature.included ? (
                          <svg className="w-4 h-4 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <svg className="w-4 h-4 text-warm-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        )}
                        <span className={`text-sm ${feature.included ? 'text-warm-700' : 'text-warm-400'}`}>
                          {feature.name}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="py-20 lg:py-32">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="inline-block px-4 py-1.5 bg-primary-50 text-primary-700 rounded-full text-sm font-medium mb-4">
              FAQ
            </span>
            <h2 className="text-3xl sm:text-4xl font-bold text-warm-900">
              Frequently asked questions
            </h2>
          </div>

          <div className="space-y-4">
            {faqs.map((faq, i) => (
              <div
                key={i}
                className="bg-white rounded-2xl border border-warm-100 shadow-soft overflow-hidden transition-all duration-200 hover:shadow-soft-lg"
              >
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-6 text-left"
                >
                  <span className="font-semibold text-warm-900 pr-4">{faq.question}</span>
                  <svg
                    className={`w-5 h-5 text-warm-400 flex-shrink-0 transition-transform duration-200 ${
                      openFaq === i ? 'rotate-180' : ''
                    }`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                <div
                  className={`overflow-hidden transition-all duration-200 ${
                    openFaq === i ? 'max-h-96 pb-6' : 'max-h-0'
                  }`}
                >
                  <p className="px-6 text-warm-600 leading-relaxed">{faq.answer}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Still have questions */}
          <div className="mt-12 text-center">
            <p className="text-warm-600 mb-4">Still have questions?</p>
            <a
              href="mailto:support@saasodoo.com"
              className="inline-flex items-center gap-2 text-primary-600 font-medium hover:text-primary-700 transition-colors"
            >
              Contact our team
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-20 lg:py-32 bg-gradient-to-br from-primary-600 to-primary-700 relative overflow-hidden">
        {/* Background decoration */}
        <div className="absolute inset-0 bg-hero-pattern opacity-10" />
        <div className="absolute top-0 right-0 w-96 h-96 bg-white/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-64 h-64 bg-accent-500/10 rounded-full blur-3xl" />

        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center relative">
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-6">
            Ready to get started?
          </h2>
          <p className="text-lg text-primary-100 mb-10 max-w-2xl mx-auto">
            Start your 14-day free trial today. No credit card required.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 bg-white text-primary-700 font-semibold px-8 py-4 rounded-xl shadow-soft hover:shadow-soft-lg hover:-translate-y-0.5 transition-all duration-200"
          >
            Start Your Free Trial
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </Link>
        </div>
      </section>
    </div>
  );
};

export default PricingPage;
