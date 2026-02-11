import React from 'react';

const Card = ({ children, className = '', onClick, hover = false }) => {
  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-lg shadow-md p-6 ${
        hover ? 'hover:shadow-lg cursor-pointer transition-shadow duration-200' : ''
      } ${className}`}
    >
      {children}
    </div>
  );
};

export default Card;
