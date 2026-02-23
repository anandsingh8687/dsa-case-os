import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import toast from 'react-hot-toast';
import { register as registerUser, login, getCurrentUser } from '../../api/services';
import { setToken, setUser } from '../../utils/auth';
import { Button, Input, Card } from '../../components/ui';
import crediloLogo from '../../assets/credilo-logo.svg';

const Register = () => {
  const [isLoading, setIsLoading] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm();

  const password = watch('password');

  const onSubmit = async (data) => {
    setIsLoading(true);
    try {
      await registerUser({
        email: data.email,
        password: data.password,
        full_name: data.name,
      });

      // Register endpoint returns profile only, so login explicitly after register.
      const loginResponse = await login({
        email: data.email,
        password: data.password,
      });
      const accessToken = loginResponse.data?.access_token;

      if (!accessToken) {
        throw new Error('Registration succeeded but login token missing');
      }

      setToken(accessToken);

      try {
        const meResponse = await getCurrentUser();
        setUser(meResponse.data);
      } catch (profileError) {
        setUser(null);
      }

      toast.success('Registration successful!');
      // Force a full page reload to ensure auth state is picked up by route guards
      window.location.href = '/dashboard';
    } catch (error) {
      toast.error(
        error.response?.data?.detail || 'Registration failed. Please try again.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-blue-100 flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <div className="text-center mb-8">
          <img
            src={crediloLogo}
            alt="Credilo logo"
            className="w-14 h-14 rounded-xl object-cover mx-auto mb-3 shadow-sm"
          />
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Credilo</h1>
          <p className="text-gray-600">Create your account</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)}>
          <Input
            label="Name"
            type="text"
            placeholder="Your name"
            error={errors.name?.message}
            {...register('name', {
              required: 'Name is required',
            })}
          />

          <Input
            label="Email"
            type="email"
            placeholder="you@example.com"
            error={errors.email?.message}
            {...register('email', {
              required: 'Email is required',
              pattern: {
                value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                message: 'Invalid email address',
              },
            })}
          />

          <Input
            label="Password"
            type="password"
            placeholder="••••••••"
            error={errors.password?.message}
            {...register('password', {
              required: 'Password is required',
              minLength: {
                value: 6,
                message: 'Password must be at least 6 characters',
              },
            })}
          />

          <Input
            label="Confirm Password"
            type="password"
            placeholder="••••••••"
            error={errors.confirmPassword?.message}
            {...register('confirmPassword', {
              required: 'Please confirm your password',
              validate: (value) =>
                value === password || 'Passwords do not match',
            })}
          />

          <Button
            type="submit"
            variant="primary"
            className="w-full mt-6"
            disabled={isLoading}
          >
            {isLoading ? 'Creating account...' : 'Sign Up'}
          </Button>
        </form>

        <div className="mt-6 text-center text-sm">
          <span className="text-gray-600">Already have an account? </span>
          <Link to="/login" className="text-primary hover:underline font-medium">
            Sign in
          </Link>
        </div>
      </Card>
    </div>
  );
};

export default Register;
