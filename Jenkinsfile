pipeline {
    agent any

    environment {
        COMPOSE_PROJECT_NAME = "autoquiz"
    }

    stages {
        stage('Clone Repository') {
            steps {
                git 'https://github.com/ABHISAM2289/Auto-quiz.git'
            }
        }

        stage('Build and Deploy') {
            steps {
                sh '''
                   cd Auto-quiz
                  docker-compose down
                  docker-compose build
                  docker-compose up -d
                  '''
            }
        }
    }

    post {
        failure {
            echo 'Build failed!'
        }
        success {
            echo 'Build and deployment successful!'
        }
    }
}
